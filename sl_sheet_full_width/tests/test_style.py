# -*- coding: utf-8 -*-
"""The rule lifts a width cap, so the test measures a sheet that would be capped.

Asserting on max-width itself would prove very little - a browser reports it
back in units of its own choosing. Giving the sheet more room than the cap and
measuring what it actually took is the question the module exists to answer.
"""
from odoo.release import version_info
from odoo.tests import HttpCase, tagged

# 18.0 moved the back end from /web to /odoo. Loading the old address still
# works, but it redirects, and a measurement taken on the page that is about to
# be replaced comes back empty.
BACKEND = '/odoo' if version_info[0] >= 18 else '/web'


@tagged('post_install', '-at_install')
class TestFullWidthSheet(HttpCase):

    def test_the_sheet_uses_the_whole_width(self):
        if version_info[0] < 16:
            # 14.0 and 15.0 evaluate browser test code against chrome's own
            # background page here, which has no stylesheets and reports every
            # element as unstyled, so the rule cannot be measured in a browser
            # on those releases. What is checked instead is the thing that
            # actually goes wrong there: whether the stylesheet reaches the
            # backend bundle at all.
            self._check_the_stylesheet_is_declared()
            return
        self.browser_js(
            BACKEND,
            """
            // Evaluated repeatedly until it says something, and the first
            // evaluations can land on chrome's own background page - which has
            // no stylesheets and would report every element as unstyled. Saying
            // nothing until there are stylesheets is what waits for the real
            // page; signalling on the first pass is what made this a race.
            if (document.styleSheets.length === 0) {
                // not on the Odoo page yet
            } else {
                // Measured against a control rather than against a number: the
                // settings page keeps its cap deliberately, so a sheet that is
                // wider than that one is a cap that was lifted. Without the module
                // both come back the same, which is what makes this a test.
                function measure(className) {
                    const probe = document.createElement('div');
                    probe.className = className;
                    probe.style.cssText = 'position:absolute; top:0; left:0; width:1300px';
                    probe.innerHTML =
                        '<div class="o_form_sheet_bg" style="width:1300px">' +
                        '<div class="o_form_sheet"></div></div>';
                    document.body.appendChild(probe);
                    const width = probe.querySelector('.o_form_sheet').getBoundingClientRect().width;
                    probe.remove();
                    return width;
                }
                const lifted = measure('o_form_view');
                const capped = measure('o_form_view o_res_config_form_view');
                if (lifted <= capped) {
                    console.error('the cap was not lifted: ' + lifted + 'px, same as the ' +
                                  'settings page at ' + capped + 'px');
                } else if (capped > 1200) {
                    console.error('the settings page lost its own width: ' + capped + 'px');
                } else {
                    console.log('test successful');
                }
            }
            """,
            login='admin')

    def _check_the_stylesheet_is_declared(self):
        if version_info[0] < 15:
            # 14.0 ignores the manifest's assets key, so the bundle is
            # inherited instead and the stylesheet is a node in it.
            view = self.env.ref('sl_sheet_full_width.web_assets_backend')
            self.assertEqual(view.inherit_id, self.env.ref('web.assets_backend'),
                             'the stylesheet is not attached to the backend bundle')
            self.assertIn('sheet_full_width.scss', view.arch,
                          'the bundle does not carry this module\'s stylesheet')
        else:
            paths = self.env['ir.asset']._get_asset_paths(
                'web.assets_backend', css=True)
            self.assertTrue(any('sheet_full_width.scss' in str(entry) for entry in paths),
                            'the stylesheet is not in the backend bundle')
