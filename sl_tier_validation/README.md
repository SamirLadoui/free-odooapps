# Approval Tiers

> Somebody Has To Agree Before A Record Moves On - On Any Model, Without Code

Somebody has to agree before a purchase order is confirmed, before a discount is given, before a holiday is granted. Odoo has no general way to say so, and most add-ons that add one need a developer for every model they apply to. This needs none.

## Features

- **Set Up By An Administrator, Not A Developer** - Pick the model, the field whose change has to be agreed to, the value that needs agreeing, and who agrees. That is the whole setup, and it works on models nobody wrote this for.
- **Tiers, In Order** - Several tiers on one model are asked in sequence, and the record cannot move until every one of them has agreed. One approval out of two is not approval - the sequence is what makes it a hierarchy rather than a crowd.
- **Only When It Matters** - A tier can carry a condition, so approval is asked for the orders above a certain amount rather than for all of them. That is the usual reason anybody wants this at all.
- **A Rejection Has To Say Why** - A refusal with no reason sends the document back with nothing to act on, so one is required before it can be recorded.
- **The Record Of Who Agreed Is Kept** - Approvals stay after they are answered - who agreed, when, and what a rejection said. Asking again starts a fresh round and the earlier one remains, so a document that went round twice shows that it did.
- **Held, Not Hidden** - While approval is outstanding the change is refused with the names of the people it is waiting on, rather than failing quietly or letting it through.
- **Costs Nothing When Unused** - The models under approval are cached, and a model with no tier on it does no extra work at all.

## Getting Started

1. Install the module and open Settings ► Approvals ► Approval Tiers.
2. Add a tier: the model, the field - usually the status - the value that needs agreeing to, and the reviewers or a group.
3. Add a condition if approval is only needed above a threshold.
4. From the record, ask for validation; the reviewers answer under Settings ► Approvals.

## Good To Know

- Only the value named on the tier is held. Everything else about the record carries on working.
- A tier with nobody to review it is refused: it could never be approved, and would stop the record for good.
- A field that does not exist on the model is refused when the tier is saved, not the first time somebody is blocked by it.
- Anybody named on the tier, or in its group, may answer it.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
