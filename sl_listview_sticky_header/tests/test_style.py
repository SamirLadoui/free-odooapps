# -*- coding: utf-8 -*-
"""A stylesheet that never reaches the browser is the whole failure mode here.

There is no python to test: the module is one scss file and a line in the
manifest, and the way it breaks is that the line is wrong and nothing happens.
So the test opens a browser, builds the markup the rule is written against,
and asks the browser what it made of it. Checking that the file exists on disk
would pass in exactly the case that matters.
"""
from odoo.release import version_info
from odoo.tests import HttpCase, tagged

# 18.0 moved the back end from /web to /odoo. Loading the old address still
# works, but it redirects, and a measurement taken on the page that is about to
# be replaced comes back empty.
BACKEND = '/odoo' if version_info[0] >= 18 else '/web'


@tagged('post_install', '-at_install')
class TestStickyHeader(HttpCase):

    def test_the_heading_row_is_pinned(self):
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
                const probe = document.createElement('div');
                probe.className = 'o_list_renderer';
                probe.style.cssText = 'position:absolute; top:0; left:0; width:900px';
                probe.innerHTML =
                    '<table class="o_list_table"><thead><tr><th>Column</th></tr></thead>' +
                    '<tfoot><tr><td>Total</td></tr></tfoot></table>';
                document.body.appendChild(probe);
                // Read the values out before the probe goes: getComputedStyle hands
                // back a live declaration, and a detached element reports nothing.
                const head = getComputedStyle(probe.querySelector('thead')).position;
                const foot = getComputedStyle(probe.querySelector('tfoot')).position;
                const background = getComputedStyle(probe.querySelector('th')).backgroundColor;
                probe.remove();
                if (head !== 'sticky') {
                    console.error('the heading row is not sticky: ' + head);
                } else if (foot !== 'sticky') {
                    console.error('the totals row is not sticky: ' + foot);
                } else if (!background || background === 'rgba(0, 0, 0, 0)') {
                    console.error('the heading is transparent, so rows show through it');
                } else {
                    console.log('test successful');
                }
            }
            """,
            login='admin')
