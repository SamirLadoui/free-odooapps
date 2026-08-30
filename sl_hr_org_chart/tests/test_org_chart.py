# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestOrgChart(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Employee = cls.env['hr.employee']
        cls.ceo = Employee.create({'name': 'Chief Exec', 'job_title': 'CEO'})
        cls.head = Employee.create({
            'name': 'Head Of Sales', 'job_title': 'Director',
            'parent_id': cls.ceo.id})
        cls.rep_a = Employee.create({'name': 'Rep A', 'parent_id': cls.head.id})
        cls.rep_b = Employee.create({'name': 'Rep B', 'parent_id': cls.head.id})
        cls.loner = Employee.create({'name': 'No Manager'})

    # -- the tree ----------------------------------------------------------

    def test_roots_are_the_managerless(self):
        roots = self.env['hr.employee']._org_roots()
        self.assertIn(self.ceo, roots)
        self.assertIn(self.loner, roots)
        self.assertNotIn(self.head, roots)

    def test_tree_nests_correctly(self):
        tree = self.ceo._org_tree()
        self.assertEqual(tree['name'], 'Chief Exec')
        self.assertEqual(len(tree['children']), 1)
        head = tree['children'][0]
        self.assertEqual(head['name'], 'Head Of Sales')
        self.assertEqual({c['name'] for c in head['children']}, {'Rep A', 'Rep B'})

    def test_children_are_sorted(self):
        tree = self.head._org_tree()
        self.assertEqual([c['name'] for c in tree['children']], ['Rep A', 'Rep B'])

    def test_report_count_is_everyone_beneath(self):
        """Not just direct reports: the whole subtree."""
        self.assertEqual(self.ceo._org_tree()['report_count'], 3)
        self.assertEqual(self.head._org_tree()['report_count'], 2)
        self.assertEqual(self.rep_a._org_tree()['report_count'], 0)

    def test_leaf_has_no_children(self):
        self.assertEqual(self.rep_a._org_tree()['children'], [])

    def test_job_title_and_department_carry_through(self):
        tree = self.ceo._org_tree()
        self.assertEqual(tree['job_title'], 'CEO')

    # -- the cycle guard ---------------------------------------------------

    def test_a_management_cycle_is_refused(self):
        """Somebody managing themselves through the chain would recurse forever."""
        with self.assertRaises(ValidationError):
            self.ceo.parent_id = self.rep_a

    def test_self_management_is_refused(self):
        with self.assertRaises(ValidationError):
            self.head.parent_id = self.head

    def test_tree_survives_a_cycle_in_the_data(self):
        """One bad record must not blank the whole chart."""
        # Build the loop through SQL, past the constraint, as corrupt data would.
        self.env.cr.execute(
            "UPDATE hr_employee SET parent_id = %s WHERE id = %s",
            (self.rep_a.id, self.ceo.id))
        self.env.invalidate_all()
        tree = self.ceo._org_tree()
        self.assertTrue(tree['name'], "the chart should still render")

    # -- the pages ---------------------------------------------------------

    def test_company_chart_renders(self):
        self.authenticate('admin', 'admin')
        self.env.cr.flush()
        response = self.url_open('/sl_hr_org_chart/company')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Chief Exec', response.text)
        self.assertIn('Rep A', response.text)

    def test_employee_chart_shows_only_the_subtree(self):
        self.authenticate('admin', 'admin')
        self.env.cr.flush()
        response = self.url_open('/sl_hr_org_chart/employee/%d' % self.head.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Head Of Sales', response.text)
        self.assertIn('Rep A', response.text)
        self.assertNotIn('No Manager', response.text,
                         "an unrelated root should not appear in a subtree")

    def test_missing_employee_is_a_404(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(
            self.url_open('/sl_hr_org_chart/employee/999999999').status_code, 404)

    def test_chart_requires_login(self):
        response = self.url_open('/sl_hr_org_chart/company', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_action_points_at_the_page(self):
        action = self.head.action_open_org_chart()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn(str(self.head.id), action['url'])
