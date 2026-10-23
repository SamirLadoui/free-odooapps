# Copyright 2026 Samir Ladoui
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAttendanceCorrection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        def user(login, groups=()):
            return cls.env['res.users'].create({
                'name': login, 'login': login,
                'company_id': cls.company.id,
                'company_ids': [(6, 0, cls.company.ids)],
                'groups_id': [(6, 0, [cls.env.ref('base.group_user').id] + [cls.env.ref(g).id for g in groups])],
            })
        cls.worker = user('correction_worker')
        cls.other = user('correction_other')
        cls.officer = user('correction_officer', ['hr_attendance.group_hr_attendance_user'])
        cls.manager = user('correction_manager', ['hr_attendance.group_hr_attendance_manager'])
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Correction worker', 'user_id': cls.worker.id,
            'company_id': cls.company.id,
        })
        cls.other_employee = cls.env['hr.employee'].create({
            'name': 'Other worker', 'user_id': cls.other.id, 'company_id': cls.company.id,
        })
        cls.attendance = cls.env['hr.attendance'].create({
            'employee_id': cls.employee.id,
            'check_in': '2026-09-01 08:00:00', 'check_out': '2026-09-01 16:00:00',
        })
        cls.Request = cls.env['sl.attendance.correction']

    def request(self, **vals):
        data = {'employee_id': self.employee.id, 'attendance_id': self.attendance.id,
                'proposed_check_in': '2026-09-01 08:00:00',
                'proposed_check_out': '2026-09-01 17:00:00', 'reason': 'Forgot to check out on time'}
        data.update(vals)
        return self.Request.with_user(self.worker).create(data)

    def test_submit_captures_authoritative_originals(self):
        request = self.request()
        request.action_submit()
        self.assertEqual(request.state, 'submitted')
        self.assertEqual(request.requester_id, self.worker)
        self.assertEqual(request.company_id, self.company)
        self.assertEqual(request.original_check_in, self.attendance.check_in)
        self.assertEqual(request.original_check_out, self.attendance.check_out)
        self.assertEqual(request.original_write_date, self.attendance.write_date)
        self.assertTrue(request.submitted_at)
        self.assertTrue(request.original_fingerprint)
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_create_rejects_protected_fields(self):
        forged = {
            'state': 'approved', 'requester_id': self.other.id, 'company_id': self.company.id,
            'original_check_in': '2020-01-01 08:00:00', 'original_check_out': '2020-01-01 09:00:00',
            'original_write_date': '2020-01-01 09:00:00', 'original_fingerprint': 'forged',
            'submitted_at': '2020-01-01 09:00:00',
            'decided_by': self.manager.id, 'decided_at': '2020-01-01 09:00:00',
            'decision_reason': 'Forged decision', 'create_uid': self.manager.id,
        }
        for field, value in forged.items():
            with self.subTest(field=field), self.assertRaises(AccessError), self.cr.savepoint():
                self.request(**{field: value})

    def test_context_defaults_cannot_forge_audit(self):
        request = self.Request.with_user(self.worker).with_context(
            default_employee_id=self.other_employee.id, default_requester_id=self.other.id,
            default_company_id=self.company.id, default_state='approved',
            default_decided_by=self.manager.id, default_decided_at='2020-01-01 09:00:00',
            default_original_check_in='2020-01-01 08:00:00', default_decision_reason='Forgery',
            default_original_fingerprint='forged',
        ).create({'proposed_check_in': '2026-09-03 08:00:00',
                  'proposed_check_out': '2026-09-03 16:00:00', 'reason': 'Missing shift'})
        self.assertEqual(request.employee_id, self.employee)
        self.assertEqual(request.requester_id, self.worker)
        self.assertEqual(request.state, 'draft')
        self.assertFalse(request.decided_by)
        self.assertFalse(request.decided_at)
        self.assertFalse(request.original_check_in)
        self.assertFalse(request.decision_reason)
        self.assertFalse(request.original_fingerprint)

    def test_write_audit_whitelist_cannot_be_bypassed_by_context(self):
        request = self.request().with_context(sl_correction_internal=True, skip_validation=True)
        forged = {'state': 'approved', 'requester_id': self.other.id,
                  'employee_id': self.other_employee.id, 'company_id': self.company.id,
                  'original_check_out': '2020-01-01 09:00:00', 'original_check_in': False,
                  'original_write_date': False, 'original_fingerprint': 'forged', 'submitted_at': False,
                  'decided_by': self.manager.id, 'decided_at': '2020-01-01 09:00:00',
                  'decision_reason': 'Forgery', 'write_uid': self.manager.id}
        for field, value in forged.items():
            with self.subTest(field=field), self.assertRaises(AccessError), self.cr.savepoint():
                request.write({field: value})

    def test_cannot_request_for_another_employee(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.request(employee_id=self.other_employee.id)

    def test_attendance_employee_ownership(self):
        foreign = self.env['hr.attendance'].create({
            'employee_id': self.other_employee.id, 'check_in': '2026-09-01 08:00:00',
            'check_out': '2026-09-01 16:00:00'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.request(attendance_id=foreign.id)

    def test_blank_reason_and_reverse_times(self):
        for vals in ({'reason': '   '}, {'proposed_check_out': '2026-09-01 07:00:00'},
                     {'proposed_check_out': '2026-09-01 08:00:00'}):
            with self.subTest(vals=vals), self.assertRaises(ValidationError), self.cr.savepoint():
                self.request(**vals)

    def test_submitted_proposals_freeze_and_cannot_be_deleted(self):
        request = self.request()
        request.action_submit()
        for vals in ({'reason': 'Rewritten'}, {'proposed_check_out': '2026-09-01 18:00:00'},
                     {'attendance_id': False}):
            with self.subTest(vals=vals), self.assertRaises(UserError), self.cr.savepoint():
                request.write(vals)
        with self.assertRaises(UserError), self.cr.savepoint():
            request.unlink()

    def test_only_requester_can_edit_draft(self):
        request = self.request()
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).write({'reason': 'Officer edit'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_submit()
        request.write({'reason': 'Employee edited draft'})
        self.assertEqual(request.reason, 'Employee edited draft')

    def test_record_rules_own_officer_and_administrator(self):
        own = self.request()
        vals = {'employee_id': self.other_employee.id,
                'proposed_check_in': '2026-09-03 08:00:00',
                'proposed_check_out': '2026-09-03 16:00:00', 'reason': 'Missing shift'}
        other = self.Request.with_user(self.other).create(vals)
        domain = [('id', 'in', (own | other).ids)]
        self.assertEqual(self.Request.with_user(self.worker).search(domain).ids, own.ids)
        self.assertEqual(set(self.Request.with_user(self.officer).search(domain).ids), {own.id, other.id})
        self.assertEqual(set(self.Request.with_user(self.manager).search(domain).ids), {own.id, other.id})
        with self.assertRaises(AccessError):
            other.with_user(self.worker).read(['reason'])

    def test_company_isolation(self):
        company = self.env['res.company'].create({'name': 'Correction isolated company'})
        employee = self.env['hr.employee'].create({
            'name': 'Worker in isolated company', 'user_id': self.worker.id, 'company_id': company.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.request(employee_id=employee.id, attendance_id=False)
        request = self.request()
        employee.write({'user_id': False})
        employee.flush(['user_id'])
        self.employee.company_id = company
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.action_submit()


    def submitted(self, **vals):
        request = self.request(**vals)
        request.action_submit()
        return request

    def test_native_officer_approval_updates_native_as_actor(self):
        request = self.submitted()
        request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(self.attendance.check_out, request.proposed_check_out)
        self.assertEqual(self.attendance.write_uid, self.officer)
        self.assertEqual(request.decided_by, self.officer)
        self.assertTrue(request.decided_at)
        self.assertTrue(request.decision_reason)
        self.assertEqual(request.original_check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_approval_respects_restrictive_native_record_rule(self):
        request = self.submitted()
        self.env['ir.rule'].create({
            'name': 'QA native attendance write restriction',
            'model_id': self.env['ir.model']._get_id('hr.attendance'),
            'domain_force': "[('id', '=', 0)]", 'perm_read': False,
            'perm_write': True, 'perm_create': True, 'perm_unlink': False,
        })
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)

    def test_draft_cannot_be_decided(self):
        request = self.request()
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_reject('Too soon')

    def test_all_attendance_manager_can_approve(self):
        request = self.submitted()
        request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(self.attendance.write_uid, self.manager)

    def test_ordinary_employee_cannot_approve_or_reject(self):
        request = self.submitted()
        for user in (self.worker, self.other):
            with self.subTest(user=user.login), self.assertRaises(AccessError), self.cr.savepoint():
                request.with_user(user).action_approve()
            with self.subTest(user=user.login), self.assertRaises(AccessError), self.cr.savepoint():
                request.with_user(user).action_reject('Unauthorized')
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)

    def test_self_approval_forbidden_even_for_all_manager(self):
        self.worker.write({'groups_id': [(4, self.env.ref('hr_attendance.group_hr_attendance_user').id)]})
        request = self.submitted()
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.action_approve()
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.action_reject('Self decision')

    def test_generic_parent_without_native_role_cannot_decide(self):
        self.employee.parent_id = self.other_employee
        request = self.submitted()
        for actor in (self.other,):
            for action, args in (('action_approve', ()), ('action_reject', ('No authority',))):
                with self.subTest(action=action), self.assertRaises(AccessError), self.cr.savepoint():
                    getattr(request.with_user(actor), action)(*args)
        # Losing the native officer role removes decision authority.
        self.officer.write({'groups_id': [(3, self.env.ref('hr_attendance.group_hr_attendance_user').id)]})
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()

    def test_missing_attendance_created_once_as_approver(self):
        request = self.submitted(attendance_id=False,
                                 proposed_check_in='2026-09-02 08:00:00',
                                 proposed_check_out='2026-09-02 16:00:00')
        self.assertFalse(request.original_check_in)
        request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'approved')
        target = request.attendance_id
        self.assertTrue(target)
        self.assertEqual(target.employee_id, self.employee)
        self.assertEqual(target.create_uid, self.officer)
        self.assertEqual(target.check_out, request.proposed_check_out)
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.employee.id), ('check_in', '=', request.proposed_check_in)]), 1)

    def test_stale_attendance_not_overwritten(self):
        request = self.submitted()
        self.attendance.write({'check_out': '2026-09-01 15:00:00'})
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 15:00:00'))
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)

    def test_target_cache_invalidated_before_stale_check(self):
        request = self.submitted()
        self.attendance.flush()
        self.assertTrue(request.with_user(self.officer).attendance_id.check_out)
        self.env.cr.execute("UPDATE hr_attendance SET check_out='2026-09-01 15:00:00' WHERE id=%s", [self.attendance.id])
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.attendance.invalidate_cache(ids=self.attendance.ids)
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 15:00:00'))

    def test_request_cache_invalidated_before_repeat_decision(self):
        request = self.submitted()
        self.assertEqual(request.with_user(self.officer).state, 'submitted')
        self.env.cr.execute("UPDATE sl_attendance_correction SET state='cancelled' WHERE id=%s", [request.id])
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_native_overlap_failure_leaves_request_and_attendance_unchanged(self):
        request = self.submitted(proposed_check_out='2026-09-01 19:00:00')
        self.env['hr.attendance'].create({'employee_id': self.employee.id,
            'check_in': '2026-09-01 18:00:00', 'check_out': '2026-09-01 20:00:00'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_at)
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_missing_proposal_cannot_duplicate_existing_shift(self):
        request = self.request(attendance_id=False)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.action_submit()

    def test_missing_conflict_created_after_submission_blocks_approval(self):
        request = self.submitted(attendance_id=False, proposed_check_in='2026-09-02 08:00:00',
                                 proposed_check_out='2026-09-02 16:00:00')
        self.env['hr.attendance'].create({'employee_id': self.employee.id,
            'check_in': '2026-09-02 09:00:00', 'check_out': '2026-09-02 10:00:00'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertFalse(request.attendance_id)
        self.assertEqual(request.state, 'submitted')

    def test_open_native_attendance_is_not_genuinely_missing(self):
        self.attendance.check_out = False
        request = self.request(attendance_id=False, proposed_check_in='2026-09-02 08:00:00',
                               proposed_check_out='2026-09-02 16:00:00')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.action_submit()

    def test_reject_requires_reason_and_records_actor_without_mutation(self):
        request = self.submitted()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.with_user(self.officer).action_reject('   ')
        request.with_user(self.officer).action_reject('Clock evidence disagrees')
        self.assertEqual(request.state, 'rejected')
        self.assertEqual(request.decided_by, self.officer)
        self.assertTrue(request.decided_at)
        self.assertEqual(request.decision_reason, 'Clock evidence disagrees')
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))
        for vals in ({'reason': 'Edited'}, {'decision_reason': 'Edited'}):
            with self.assertRaises(UserError), self.cr.savepoint():
                request.write(vals)
        with self.assertRaises(UserError), self.cr.savepoint():
            request.unlink()
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()

    def test_requester_can_cancel_draft_or_submitted_only(self):
        for submit in (False, True):
            request = self.request()
            if submit:
                request.action_submit()
            with self.assertRaises(AccessError), self.cr.savepoint():
                request.with_user(self.officer).action_cancel()
            request.action_cancel()
            self.assertEqual(request.state, 'cancelled')
            self.assertEqual(request.decided_by, self.worker)
            self.assertTrue(request.decided_at)
            with self.assertRaises(UserError), self.cr.savepoint():
                request.write({'reason': 'Edited'})
            with self.assertRaises(UserError), self.cr.savepoint():
                request.unlink()
            with self.assertRaises(UserError), self.cr.savepoint():
                request.action_submit()

    def test_approved_snapshot_and_decision_immutable(self):
        request = self.submitted()
        request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'approved')
        for vals in ({'original_check_out': False}, {'decided_by': self.manager.id},
                     {'decided_at': False}, {'state': 'draft'}, {'reason': 'Edited'},
                     {'proposed_check_out': '2026-09-01 20:00:00'}, {'attendance_id': False}):
            with self.subTest(vals=vals), self.assertRaises(UserError), self.cr.savepoint():
                request.with_user(self.manager).with_context(sl_correction_internal=True).write(vals)
        with self.assertRaises(UserError), self.cr.savepoint():
            request.action_cancel()
        with self.assertRaises(UserError), self.cr.savepoint():
            request.unlink()

    def test_native_ordering_and_overlap_constraints_remain_active(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.attendance.with_user(self.officer).write({'check_out': '2026-09-01 07:00:00'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['hr.attendance'].with_user(self.officer).create({
                'employee_id': self.employee.id, 'check_in': '2026-09-01 09:00:00',
                'check_out': '2026-09-01 12:00:00'})

    def test_backend_views_and_employee_form(self):
        from odoo.tests import Form
        request = self.Request.with_user(self.worker)
        for kind in ('tree', 'form', 'search'):
            view = self.env.ref('sl_attendance_correction.view_correction_' + ('list' if kind == 'tree' else kind),
                                raise_if_not_found=False)
            self.assertTrue(view, 'A usable ' + kind + ' view is required')
            request.fields_view_get(view.id, kind)
        with Form(request, view='sl_attendance_correction.view_correction_form') as form:
            form.proposed_check_in = '2026-09-03 08:00:00'
            form.proposed_check_out = '2026-09-03 16:00:00'
            form.reason = 'Forgot the whole shift'
            created = form.save()
        self.assertEqual(created.employee_id, self.employee)
        self.assertEqual(created.requester_id, self.worker)
        self.assertEqual(created.state, 'draft')
        self.assertTrue(created.is_requester)
        self.assertFalse(created.can_decide)

    def test_rejection_wizard_checks_actor_and_reason(self):
        request = self.submitted()
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.action_open_reject()
        action = request.with_user(self.officer).action_open_reject()
        self.assertEqual(action['res_model'], 'sl.attendance.correction.reject')
        wizard = self.env[action['res_model']].with_user(self.officer).with_context(action['context']).create({
            'reason': 'Insufficient evidence'})
        self.assertEqual(wizard.request_id, request)
        wizard.action_reject()
        self.assertEqual(request.state, 'rejected')
        self.assertEqual(request.decision_reason, 'Insufficient evidence')
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_reject()

    def test_audit_chatter_is_escaped_honest_and_does_not_send_mail(self):
        mail_count = self.env['mail.mail'].search_count([])
        request = self.submitted(reason='<b>Forgot punch</b>')
        request.with_user(self.officer).action_approve()
        bodies = '\n'.join(request.message_ids.mapped('body'))
        self.assertIn('2026-09-01 16:00:00', bodies)
        self.assertIn('2026-09-01 17:00:00', bodies)
        self.assertIn('Applied attendance', bodies)
        self.assertIn('&lt;b&gt;Forgot punch&lt;/b&gt;', bodies)
        self.assertNotIn('<b>Forgot punch</b>', bodies)
        self.assertEqual(self.env['mail.mail'].search_count([]), mail_count)

    def test_cancelled_draft_does_not_claim_a_submission_snapshot(self):
        request = self.request()
        request.action_cancel()
        body = '\n'.join(request.message_ids.mapped('body'))
        self.assertIn('No submission snapshot was captured', body)
        self.assertFalse(request.submitted_at)
        self.assertFalse(request.original_check_in)

    def test_missing_creation_respects_native_create_rules(self):
        request = self.submitted(attendance_id=False,
                                 proposed_check_in='2026-09-03 08:00:00',
                                 proposed_check_out='2026-09-03 16:00:00')
        self.env['ir.rule'].create({
            'name': 'QA disallow native attendance create',
            'model_id': self.env['ir.model']._get_id('hr.attendance'),
            'domain_force': "[('id', '=', 0)]", 'perm_read': False,
            'perm_write': False, 'perm_create': True, 'perm_unlink': False,
        })
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.attendance_id)
        self.assertFalse(request.decided_by)

    def test_native_write_date_only_change_is_stale(self):
        request = self.submitted()
        self.attendance.flush()
        self.env.cr.execute("UPDATE hr_attendance SET write_date=write_date + interval '1 second' WHERE id=%s", [self.attendance.id])
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')

    def test_attendance_reassignment_after_submission_is_refused(self):
        request = self.submitted()
        self.attendance.write({'employee_id': self.other_employee.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, 'submitted')

    def test_all_manager_record_rules_still_require_allowed_company(self):
        company = self.env['res.company'].create({'name': 'Correction other allowed company'})
        self.worker.write({'company_ids': [(4, company.id)]})
        self.manager.write({'company_ids': [(4, company.id)]})
        employee = self.env['hr.employee'].create({
            'name': 'Worker second company', 'user_id': self.worker.id, 'company_id': company.id})
        request = self.Request.with_user(self.worker).with_context(allowed_company_ids=[company.id]).create({
            'proposed_check_in': '2026-09-03 08:00:00',
            'proposed_check_out': '2026-09-03 16:00:00', 'reason': 'Missing shift in second company'})
        request.action_submit()
        self.assertEqual(request.employee_id, employee)
        hidden = self.Request.with_user(self.manager).with_context(allowed_company_ids=[self.company.id])
        self.assertFalse(hidden.search([('id', '=', request.id)]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            hidden.browse(request.id).action_approve()
        request.with_user(self.manager).with_context(allowed_company_ids=[company.id]).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.attendance_id.employee_id.company_id, company)

    def test_whole_approval_rolls_back_when_audit_logging_fails(self):
        from unittest.mock import patch
        request = self.submitted()
        with patch.object(type(request), '_audit_note', side_effect=UserError('QA audit failure')):
            try:
                request.with_user(self.officer).action_approve()
            except UserError as error:
                self.assertIn('QA audit failure', str(error))
            else:
                self.fail('Expected logging failure')
        # No assertRaises outer savepoint: the action itself must roll back.
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_closing_existing_open_attendance_preserves_open_original(self):
        self.attendance.check_out = False
        request = self.submitted()
        self.assertFalse(request.original_check_out)
        request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertFalse(request.original_check_out)
        self.assertEqual(self.attendance.check_out, request.proposed_check_out)

    def test_native_target_defaults_cannot_spoof_missing_creation(self):
        request = self.submitted(attendance_id=False, proposed_check_in='2026-09-03 08:00:00',
                                 proposed_check_out='2026-09-03 16:00:00')
        request.with_user(self.officer).with_context(
            default_employee_id=self.other_employee.id, default_check_in='2020-01-01 08:00:00',
            default_check_out='2020-01-01 09:00:00', default_create_uid=self.manager.id,
            default_original_check_in='2020-01-01 08:00:00', default_state='draft',
        ).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.attendance_id.employee_id, self.employee)
        self.assertEqual(request.attendance_id.create_uid, self.officer)
        self.assertEqual(request.attendance_id.check_in, request.proposed_check_in)
        self.assertFalse(request.original_check_in)

    def test_private_transaction_guard_has_no_employee_mutation_api(self):
        guard = self.env['sl.attendance.correction.guard'].with_user(self.worker)
        with self.assertRaises(AccessError), self.cr.savepoint():
            guard.create({'employee_id': self.employee.id, 'revision': 1})
        request = self.submitted()
        request.with_user(self.officer).action_approve()
        existing = self.env['sl.attendance.correction.guard'].search([('employee_id', '=', self.employee.id)])
        self.assertTrue(existing)
        with self.assertRaises(AccessError), self.cr.savepoint():
            existing.with_user(self.officer).write({'revision': 0})
        with self.assertRaises(AccessError), self.cr.savepoint():
            existing.with_user(self.officer).unlink()

    def test_any_native_stored_change_is_stale_even_with_same_write_date(self):
        request = self.submitted()
        self.attendance.write({'worked_hours': 7.5})
        self.assertEqual(self.attendance.worked_hours, 7.5)
        self.attendance.flush()
        # Odoo caches cr.now() within this transaction; write_date alone is not
        # a sufficient version token for batch/server-action callers.
        self.assertEqual(self.attendance.write_date, request.original_write_date)
        with self.assertRaises(UserError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_native_attendance_rights_are_not_granted(self):
        # Native ACL/rules permit own writes. Disable unrelated HR prefetch:
        # unchanged biometric private fields are absent on hr.employee.public.
        native = self.attendance.with_context(prefetch_fields=False)
        native.with_user(self.worker).write({'check_out': '2026-09-01 17:00:00'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            native.with_user(self.other).write({'check_out': '2026-09-01 18:00:00'})

    def _assert_external_acl_denied(self, actor):
        for model in ('sl.attendance.correction', 'sl.attendance.correction.reject',
                      'sl.attendance.correction.guard'):
            for operation in ('read', 'write', 'create', 'unlink'):
                with self.subTest(model=model, operation=operation):
                    self.assertFalse(self.env[model].with_user(actor).check_access_rights(
                        operation, raise_exception=False))
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.Request.with_user(actor).create({'proposed_check_in': '2026-09-03 08:00:00',
                'proposed_check_out': '2026-09-03 16:00:00', 'reason': 'External request'})
        request = self.request()
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(actor).read(['reason'])

    def test_public_acl_denied(self):
        self._assert_external_acl_denied(self.env.ref('base.public_user'))

    def test_portal_acl_denied(self):
        portal = self.env['res.users'].create({'name': 'Correction portal', 'login': 'correction_portal',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)]})
        self._assert_external_acl_denied(portal)

    def test_same_company_user_reassignment_blocks_submission(self):
        request = self.request()
        self.employee.user_id = False
        self.other_employee.user_id = False
        self.employee.user_id = self.other
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.action_submit()
        self.assertEqual(request.state, 'draft')
        self.assertFalse(request.submitted_at)

    def test_same_company_user_reassignment_blocks_approval(self):
        request = self.submitted()
        self.employee.user_id = False
        self.other_employee.user_id = False
        self.employee.user_id = self.other
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_approve()
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)
        self.assertEqual(self.attendance.check_out, fields.Datetime.to_datetime('2026-09-01 16:00:00'))

    def test_same_company_user_reassignment_blocks_rejection(self):
        request = self.submitted()
        self.employee.user_id = False
        self.other_employee.user_id = False
        self.employee.user_id = self.other
        with self.assertRaises(AccessError), self.cr.savepoint():
            request.with_user(self.officer).action_reject('Ownership changed')
        self.assertEqual(request.state, 'submitted')
        self.assertFalse(request.decided_by)

    def test_rejection_form_requires_reason(self):
        from odoo.tests import Form
        request = self.submitted()
        action = request.with_user(self.officer).action_open_reject()
        model = self.env[action['res_model']].with_user(self.officer).with_context(action['context'])
        form = Form(model, view='sl_attendance_correction.view_correction_reject_form')
        with self.assertRaises(AssertionError):
            form.save()
        form.reason = '   '
        wizard = form.save()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_reject()
        wizard.reason = 'Evidence does not support the proposal'
        wizard.action_reject()
        self.assertEqual(request.state, 'rejected')
