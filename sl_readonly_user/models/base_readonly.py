# -*- coding: utf-8 -*-
"""A user who can look at everything and change nothing.

The auditor, the accountant's assistant, the owner who wants to see the
numbers on holiday. Odoo can express this only by going through every model
in the access rights table and unticking three boxes each, which nobody
finishes and nobody maintains afterwards.

This is one group. A user who has it is refused every create, write and
delete, whatever the access rights say, on every model at once.

The check sits where Odoo already asks whether an operation is allowed, so
there is nothing to route around: the web client, an import, an automated
action and an XML-RPC call all pass through it.
"""
from odoo import _, models, release
from odoo.exceptions import AccessError

WRITING = ('create', 'write', 'unlink')

# What the web client writes to simply in order to work. Refusing these
# protects no business data; it only produces an error dialog on every page.
ALWAYS_ALLOWED = (
    'res.users.settings',    # what the client remembers per user, 17.0 on
    'res.users.log',         # written once, at login
    'bus.presence',          # written on every poll
    'mail.notification',     # marking a message as read changes no data
)


class Base(models.AbstractModel):
    _inherit = 'base'

    def _sl_read_only_denied(self, operation):
        """Whether this operation is refused for being a change."""
        if operation not in WRITING:
            return False
        if self.env.su or not self.env.uid:
            # Odoo's own machinery runs as superuser; refusing it would break
            # logging in rather than protect anything.
            return False
        if self._name in ALWAYS_ALLOWED:
            return False
        return self.env.user._sl_is_read_only()

    def _sl_read_only_error(self):
        return AccessError(_(
            'This account can look at %s but not change it. It is a read-only '
            'account.', self._description or self._name))


# check_access replaced check_access_rights in 18.0, and both are the point
# every create, write and delete passes through on their own release.
if release.version_info[0] >= 18:

    class BaseReadOnlyAccess(models.AbstractModel):
        _inherit = 'base'

        def check_access(self, operation):
            if self._sl_read_only_denied(operation):
                raise self._sl_read_only_error()
            return super().check_access(operation)

        def has_access(self, operation):
            # Answered as well as raised, so the client greys the button out
            # rather than offering it and then refusing.
            if self._sl_read_only_denied(operation):
                return False
            return super().has_access(operation)

else:

    class BaseReadOnlyAccess(models.AbstractModel):
        _inherit = 'base'

        def check_access_rights(self, operation, raise_exception=True):
            if self._sl_read_only_denied(operation):
                if raise_exception:
                    raise self._sl_read_only_error()
                return False
            return super().check_access_rights(
                operation, raise_exception=raise_exception)
