# -*- coding: utf-8 -*-
import base64
import io
import json
import re
import zipfile
from datetime import datetime

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Bookkeeping Odoo maintains itself; exporting it would be noise at best and
# wrong at worst.
SKIP_FIELDS = {
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
    '__last_update', 'display_name',
}
# Relational kinds we cannot express reliably as portable XML.
SKIP_TYPES = {'one2many', 'many2many', 'binary'}

VALID_NAME = re.compile(r'^[a-z][a-z0-9_]*$')


class ModuleRecord(models.Model):
    _name = 'sl.module.record'
    _description = 'Configuration Recording'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, help="What you are capturing, in plain words.")
    technical_name = fields.Char(
        required=True, default='my_configuration',
        help="The generated module's directory name. Lowercase, no spaces.")
    summary = fields.Char(default='Configuration captured from a running database')
    author = fields.Char(default=lambda self: self.env.company.name)
    website = fields.Char(default=lambda self: self.env.company.website)
    module_version = fields.Char(default='1.0.0')
    module_license = fields.Selection(
        [('LGPL-3', 'LGPL-3'), ('AGPL-3', 'AGPL-3'), ('OPL-1', 'OPL-1')],
        default='LGPL-3', required=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('recording', 'Recording'), ('stopped', 'Stopped')],
        default='draft', required=True)
    date_start = fields.Datetime(readonly=True)
    date_stop = fields.Datetime(readonly=True)

    model_ids = fields.Many2many(
        'ir.model', string='Models To Watch', required=True,
        domain="[('transient', '=', False)]",
        help="Only changes to these models are captured.")
    line_ids = fields.One2many('sl.module.record.line', 'record_id', string='Captured')
    line_count = fields.Integer(compute='_compute_line_count')

    boundary_json = fields.Text(
        readonly=True, copy=False,
        help="Highest id per watched model when recording started. Used to tell "
             "a newly created record from an edited one.")

    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.constrains('technical_name')
    def _check_technical_name(self):
        for record in self:
            if not VALID_NAME.match(record.technical_name or ''):
                raise ValidationError(_(
                    "'%s' is not a valid module name. Use lowercase letters, "
                    "digits and underscores, starting with a letter.")
                    % record.technical_name)

    # -- recording ---------------------------------------------------------

    def _snapshot_boundaries(self):
        """Highest existing id per watched model.

        PostgreSQL's now() is transaction-scoped, so create_date and write_date
        are identical for everything written in one transaction and cannot tell
        a create from an update. Ids can.
        """
        self.ensure_one()
        boundaries = {}
        for model in self.model_ids:
            target = self.env.get(model.model)
            if target is None or not target._auto:
                continue
            newest = target.search([], order='id desc', limit=1)
            boundaries[model.model] = newest.id if newest else 0
        return boundaries

    def action_start(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.write({
            'state': 'recording',
            'date_start': fields.Datetime.now(),
            'date_stop': False,
            'boundary_json': json.dumps(self._snapshot_boundaries()),
        })
        return True

    def action_stop(self):
        self.ensure_one()
        if self.state != 'recording':
            raise UserError(_("This recording is not running."))
        self.date_stop = fields.Datetime.now()
        self._collect_changes()
        self.state = 'stopped'
        return True

    def action_reset(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.write({'state': 'draft', 'date_start': False, 'date_stop': False,
                    'boundary_json': False, 'file_data': False, 'file_name': False})
        return True

    def _collect_changes(self):
        """Find what changed in the watched models during the window.

        Ids and timestamps rather than ORM hooks: nothing is patched, nothing is
        slowed down while not recording, and a recording survives a restart.
        Anything with an id above the start-of-recording boundary is new;
        anything at or below it that was touched inside the window is an edit.
        """
        self.ensure_one()
        start = self.date_start
        boundaries = json.loads(self.boundary_json or '{}')
        Line = self.env['sl.module.record.line']
        self.line_ids.unlink()

        for model in self.model_ids:
            target = self.env.get(model.model)
            if target is None or not target._auto:
                continue
            boundary = boundaries.get(model.model, 0)
            try:
                created = target.search([('id', '>', boundary)])
                # No upper bound: collection happens at stop time, so the
                # window is already closed. Comparing a Python wall clock
                # against PostgreSQL's transaction clock only adds skew.
                edited = target.search([
                    ('id', '<=', boundary), ('write_date', '>', start),
                ])
            except Exception:
                # Some models have no write_date or refuse a plain search.
                continue
            for candidate, operation in (
                    [(rec, 'created') for rec in created]
                    + [(rec, 'updated') for rec in edited]):
                Line.create({
                    'record_id': self.id,
                    'model_id': model.id,
                    'res_id': candidate.id,
                    'res_name': candidate.display_name or str(candidate.id),
                    'operation': operation,
                })
        return True

    # -- generating the module ---------------------------------------------

    def _xml_id_for(self, record):
        """A stable xmlid: the record's own if it has one, else a generated one."""
        self.ensure_one()
        existing = record.get_external_id().get(record.id)
        if existing:
            return existing, True
        return '%s.%s_%s' % (
            self.technical_name, record._name.replace('.', '_'), record.id), False

    def _exportable_fields(self, record):
        """Fields worth writing out: stored, writable, and expressible as XML."""
        result = []
        for name, field in sorted(record._fields.items()):
            if name in SKIP_FIELDS or field.type in SKIP_TYPES:
                continue
            if not field.store or field.compute and not field.inverse:
                continue
            if field.readonly and not field.related:
                continue
            result.append((name, field))
        return result

    def _record_to_xml(self, record):
        """One <record> element for one database row."""
        self.ensure_one()
        xml_id, _existing = self._xml_id_for(record)
        node = etree.Element('record', id=xml_id.split('.', 1)[-1], model=record._name)

        for name, field in self._exportable_fields(record):
            value = record[name]
            if value is False or value is None or value == '':
                continue
            child = etree.SubElement(node, 'field', name=name)
            if field.type == 'many2one':
                target_xml_id = value.get_external_id().get(value.id)
                if target_xml_id:
                    child.set('ref', target_xml_id)
                else:
                    # No xmlid on the target means the id would not survive an
                    # install elsewhere, so the link is left out deliberately.
                    node.remove(child)
                    continue
            elif field.type == 'boolean':
                child.set('eval', 'True' if value else 'False')
            elif field.type in ('integer', 'float', 'monetary'):
                child.set('eval', str(value))
            elif field.type in ('date', 'datetime'):
                child.text = str(value)
            else:
                child.text = str(value)
        return node

    def _build_data_xml(self):
        """The whole data file, as bytes."""
        self.ensure_one()
        root = etree.Element('odoo')
        data = etree.SubElement(root, 'data', noupdate='0')
        for line in self.line_ids.filtered('included'):
            target = self.env.get(line.model_id.model)
            if target is None:
                continue
            record = target.browse(line.res_id).exists()
            if not record:
                continue
            data.append(self._record_to_xml(record))
        return etree.tostring(
            root, pretty_print=True, xml_declaration=True, encoding='utf-8')

    def _build_manifest(self):
        self.ensure_one()
        return (
            "# -*- coding: utf-8 -*-\n"
            "{\n"
            "    'name': %(name)r,\n"
            "    'version': %(version)r,\n"
            "    'summary': %(summary)r,\n"
            "    'author': %(author)r,\n"
            "    'website': %(website)r,\n"
            "    'license': %(license)r,\n"
            "    'category': 'Technical',\n"
            "    'depends': ['base'],\n"
            "    'data': ['data/configuration.xml'],\n"
            "    'installable': True,\n"
            "}\n" % {
                'name': self.name,
                'version': self.module_version or '1.0.0',
                'summary': self.summary or '',
                'author': self.author or '',
                'website': self.website or '',
                'license': self.module_license,
            })

    def _build_zip(self):
        self.ensure_one()
        stream = io.BytesIO()
        root = self.technical_name
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('%s/__init__.py' % root, '')
            archive.writestr('%s/__manifest__.py' % root, self._build_manifest())
            archive.writestr('%s/data/configuration.xml' % root, self._build_data_xml())
        return stream.getvalue()

    def action_export(self):
        self.ensure_one()
        if not self.line_ids.filtered('included'):
            raise UserError(_(
                "Nothing selected to export. Record some changes first, or tick "
                "at least one captured line."))
        self.write({
            'file_data': base64.b64encode(self._build_zip()),
            'file_name': '%s.zip' % self.technical_name,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }


class ModuleRecordLine(models.Model):
    _name = 'sl.module.record.line'
    _description = 'Captured Change'
    _order = 'model_id, res_id'

    record_id = fields.Many2one('sl.module.record', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', store=True)
    res_id = fields.Integer(string='Record ID', required=True)
    res_name = fields.Char(string='Record')
    operation = fields.Selection(
        [('created', 'Created'), ('updated', 'Updated')], required=True)
    included = fields.Boolean(
        default=True, help="Untick to leave this row out of the generated module.")
