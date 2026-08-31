# School

> Academic Years, Classes, Subjects, Teachers And Student Enrolment

The core record-keeping a school runs on: who is in which class, who teaches what, and who has a seat. Built around a live seat count, so the class list is always something you can trust.

## Features

- **Academic Years That Mean Something** - Everything hangs off an academic year with a start and an end. Only one year can be running over a given period, so the current class list always means one thing.
- **Classes With Real Capacity** - A grade and an optional division, its class teacher and its subjects, with a seat limit that is actually enforced. Enrolling past capacity is refused, and a student leaving frees their seat immediately.
- **Enrolment As A Workflow** - Students start as applications and are enrolled into a class. Enrolment checks the class has room and creates a contact record, so the student can be emailed or invoiced from day one.
- **Numbering Done For You** - Student and staff numbers come from sequences. Roll numbers are unique within a class but reusable across classes, which is how a register actually works.
- **Teachers And Subjects** - Teachers with staff numbers, qualifications, subjects and the classes they manage. Subjects with codes, credits, theory or practical type, and an elective flag students can choose from.
- **Two Access Levels** - School User can read everything and enter student data. School Administrator controls academic years, classes and teachers. Nothing is visible to users outside the school groups.

## Getting Started

1. Install the module and open the School app.
2. Under Configuration, create an academic year and press Open Year.
3. Under Organisation, add your subjects, teachers, and then your classes.
4. Register students, then press Enrol to assign them a seat.

## Good To Know

- A class capacity of zero means no limit.
- Only enrolled students take up a seat; applications do not.
- Age is computed from the date of birth, and a date of birth in the future is refused.
- Enrolling a student creates a linked contact record, so existing Odoo invoicing and mailing work without extra setup.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
