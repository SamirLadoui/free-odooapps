# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _sl_hidden_menu_ids(self):
        """Menu ids hidden for the current user, including their children.

        Hiding a parent has to hide what is under it, or the child menus are
        left stranded in the app switcher with no way back to them.
        """
        user = self.env.user
        hidden = user.sudo().hidden_menu_ids
        if not hidden:
            return []
        # Straight to SQL on parent_path rather than search(): ir.ui.menu.search
        # filters by visibility, which calls back into here and recurses until
        # the stack gives out.
        # parent_path looks like "72/73/" with no leading slash, so a menu at
        # the root of the path needs its own pattern as well as the nested one.
        self.env.flush_all() if hasattr(self.env, 'flush_all') else None
        patterns = []
        for menu_id in hidden.ids:
            patterns.append('%d/%%' % menu_id)
            patterns.append('%%/%d/%%' % menu_id)
        self.env.cr.execute(
            "SELECT id FROM ir_ui_menu WHERE parent_path LIKE ANY(%s)",
            (patterns,))
        found = [row[0] for row in self.env.cr.fetchall()]
        # Union with the hidden ids themselves: parent_path is only populated
        # once the record has been flushed.
        return list(set(found) | set(hidden.ids))

    def _visible_menu_ids(self, debug=False):
        """Odoo's own visibility, minus whatever this user has hidden."""
        visible = super()._visible_menu_ids(debug=debug)
        hidden = set(self._sl_hidden_menu_ids())
        if not hidden:
            return visible
        return {menu_id for menu_id in visible if menu_id not in hidden}
