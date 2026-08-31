# -*- coding: utf-8 -*-
import base64
import io
import zipfile
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestModuleRecord(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.category_model = cls.env['ir.model']._get('res.partner.category')

    def _recording(self, models_=None, **values):
        return self.env['sl.module.record'].create(dict({
            'name': 'Test Capture',
            'technical_name': 'test_capture',
            'model_ids': [(6, 0, (models_ or self.partner_model).ids)],
        }, **values))

    # -- naming ------------------------------------------------------------

    def test_technical_name_is_validated(self):
        for bad in ('Has Spaces', '9leading', 'Upper', 'dash-name', ''):
            with self.assertRaises(ValidationError, msg='accepted %r' % bad):
                self._recording(technical_name=bad)

    def test_good_technical_names_pass(self):
        for good in ('my_module', 'a', 'x9_y'):
            self.assertTrue(self._recording(technical_name=good))

    # -- the recording window ----------------------------------------------

    def test_starting_marks_the_time(self):
        recording = self._recording()
        recording.action_start()
        self.assertEqual(recording.state, 'recording')
        self.assertTrue(recording.date_start)

    def test_stopping_requires_a_running_recording(self):
        recording = self._recording()
        with self.assertRaises(UserError):
            recording.action_stop()

    def test_changes_inside_the_window_are_captured(self):
        recording = self._recording()
        recording.action_start()
        partner = self.env['res.partner'].create({'name': 'Captured Partner'})
        recording.action_stop()

        captured = recording.line_ids.filtered(lambda l: l.res_id == partner.id)
        self.assertTrue(captured, "a partner created while recording should be caught")
        self.assertEqual(captured.operation, 'created')
        self.assertEqual(captured.model_name, 'res.partner')

    def test_changes_before_the_window_are_ignored(self):
        """PostgreSQL now() is transaction-scoped, so the pre-existing record's
        write_date has to be pushed back explicitly to model a real window."""
        earlier = self.env['res.partner'].create({'name': 'Before Recording'})
        self.env.cr.flush()
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = write_date - interval '1 day' "
            "WHERE id = %s", (earlier.id,))
        earlier.invalidate_cache(['write_date'])

        recording = self._recording()
        recording.action_start()
        recording.action_stop()
        self.assertFalse(recording.line_ids.filtered(lambda l: l.res_id == earlier.id))

    def test_unwatched_models_are_ignored(self):
        recording = self._recording()
        recording.action_start()
        tag = self.env['res.partner.category'].create({'name': 'Unwatched Tag'})
        recording.action_stop()
        self.assertFalse(
            recording.line_ids.filtered(lambda l: l.model_name == 'res.partner.category'),
            "only the watched models should be captured")

    def test_updates_are_marked_as_updates(self):
        """A record that existed before Start is an edit, however fast the
        clock: the id boundary decides, not the timestamp."""
        partner = self.env['res.partner'].create({'name': 'Existing'})
        self.env.cr.flush()
        recording = self._recording()
        recording.action_start()
        # In real use, Start and the edit are separate transactions so the edit's
        # write_date is strictly later. Inside one test transaction every
        # timestamp is identical, so the window start is moved back to model it.
        recording.date_start = recording.date_start - timedelta(minutes=5)
        partner.function = 'Buyer'
        self.env.cr.flush()
        recording.action_stop()
        line = recording.line_ids.filtered(lambda l: l.res_id == partner.id)
        self.assertEqual(line.operation, 'updated')

    def test_records_created_after_start_are_creations(self):
        recording = self._recording()
        recording.action_start()
        fresh = self.env['res.partner'].create({'name': 'Brand New'})
        recording.action_stop()
        line = recording.line_ids.filtered(lambda l: l.res_id == fresh.id)
        self.assertEqual(line.operation, 'created')

    def test_reset_clears_everything(self):
        recording = self._recording()
        recording.action_start()
        self.env['res.partner'].create({'name': 'Doomed'})
        recording.action_stop()
        self.assertTrue(recording.line_ids)
        recording.action_reset()
        self.assertEqual(recording.state, 'draft')
        self.assertFalse(recording.line_ids)
        self.assertFalse(recording.date_start)

    # -- XML generation ----------------------------------------------------

    def test_record_becomes_xml(self):
        recording = self._recording()
        partner = self.env['res.partner'].create({
            'name': 'XML Partner', 'function': 'Tester', 'city': 'Algiers'})
        node = recording._record_to_xml(partner)
        self.assertEqual(node.tag, 'record')
        self.assertEqual(node.get('model'), 'res.partner')
        names = {child.get('name') for child in node}
        self.assertIn('name', names)
        self.assertIn('city', names)

    def test_bookkeeping_fields_are_not_exported(self):
        recording = self._recording()
        partner = self.env['res.partner'].create({'name': 'XML Partner'})
        names = {child.get('name') for child in recording._record_to_xml(partner)}
        for unwanted in ('create_uid', 'create_date', 'write_uid', 'write_date',
                         'id', 'display_name'):
            self.assertNotIn(unwanted, names)

    def test_x2many_fields_are_not_exported(self):
        """They cannot be expressed portably, so they are left out on purpose."""
        recording = self._recording()
        tag = self.env['res.partner.category'].create({'name': 'A Tag'})
        partner = self.env['res.partner'].create({
            'name': 'Tagged', 'category_id': [(6, 0, tag.ids)]})
        names = {child.get('name') for child in recording._record_to_xml(partner)}
        self.assertNotIn('category_id', names)
        self.assertNotIn('child_ids', names)

    def test_many2one_uses_a_ref_when_the_target_has_an_xmlid(self):
        recording = self._recording()
        country = self.env.ref('base.dz')
        partner = self.env['res.partner'].create({
            'name': 'With Country', 'country_id': country.id})
        node = recording._record_to_xml(partner)
        country_field = node.find("field[@name='country_id']")
        self.assertIsNotNone(country_field)
        self.assertEqual(country_field.get('ref'), 'base.dz')

    def test_many2one_is_dropped_when_the_target_has_no_xmlid(self):
        """A raw database id would not survive an install elsewhere."""
        recording = self._recording()
        parent = self.env['res.partner'].create({'name': 'No XmlId Parent'})
        child = self.env['res.partner'].create({
            'name': 'Child', 'parent_id': parent.id})
        node = recording._record_to_xml(child)
        self.assertIsNone(node.find("field[@name='parent_id']"))

    def test_booleans_are_evalled(self):
        recording = self._recording()
        partner = self.env['res.partner'].create({'name': 'Company', 'is_company': True})
        node = recording._record_to_xml(partner)
        is_company = node.find("field[@name='is_company']")
        self.assertEqual(is_company.get('eval'), 'True')

    def test_data_file_is_well_formed(self):
        recording = self._recording()
        recording.action_start()
        self.env['res.partner'].create({'name': 'In The File'})
        recording.action_stop()
        parsed = etree.fromstring(recording._build_data_xml())
        self.assertEqual(parsed.tag, 'odoo')
        self.assertTrue(parsed.findall('.//record'))

    def test_excluded_lines_are_left_out(self):
        recording = self._recording()
        recording.action_start()
        partner = self.env['res.partner'].create({'name': 'Excluded Partner'})
        recording.action_stop()
        recording.line_ids.filtered(lambda l: l.res_id == partner.id).included = False
        self.assertNotIn(b'Excluded Partner', recording._build_data_xml())

    # -- the archive -------------------------------------------------------

    def test_manifest_carries_the_details(self):
        recording = self._recording(module_version='2.1.0', author='Someone')
        manifest = recording._build_manifest()
        self.assertIn("'version': '2.1.0'", manifest)
        self.assertIn("'author': 'Someone'", manifest)
        self.assertIn("'license': 'LGPL-3'", manifest)

    def test_zip_has_the_expected_shape(self):
        recording = self._recording()
        recording.action_start()
        self.env['res.partner'].create({'name': 'Zipped'})
        recording.action_stop()
        with zipfile.ZipFile(io.BytesIO(recording._build_zip())) as archive:
            names = archive.namelist()
        self.assertIn('test_capture/__manifest__.py', names)
        self.assertIn('test_capture/__init__.py', names)
        self.assertIn('test_capture/data/configuration.xml', names)

    def test_export_produces_a_download(self):
        recording = self._recording()
        recording.action_start()
        self.env['res.partner'].create({'name': 'Downloadable'})
        recording.action_stop()
        action = recording.action_export()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertTrue(recording.file_name.endswith('.zip'))
        self.assertTrue(base64.b64decode(recording.file_data))

    def test_export_with_nothing_selected_explains_itself(self):
        recording = self._recording()
        recording.action_start()
        recording.action_stop()
        recording.line_ids.write({'included': False})
        with self.assertRaises(UserError):
            recording.action_export()
