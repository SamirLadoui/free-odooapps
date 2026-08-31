# -*- coding: utf-8 -*-
{
    'name': 'Task Timer',
    'version': '15.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Start and stop a timer on a task; the time lands on a timesheet',
    'description': """
Task Timer
==========

Press Start when you begin work on a task and Stop when you finish. The elapsed
time becomes a timesheet entry, with no arithmetic and no remembering.

One timer at a time
-------------------
You cannot start a second timer while one is running. Two timers at once means
at least one of them is recording hours you were not spending, and the whole
point of a timesheet is that it is true.

Trying to start a second one names the task the first is on, so you can go and
deal with it rather than hunting for it.

Nothing is recorded by accident
-------------------------------
* Stopping under a minute after starting records **nothing**. That is a misclick,
  not work. The timer is stopped and you are told.
* **Discard Timer** throws the running time away deliberately, for when you
  started the wrong task.
* A timer belongs to the person who started it. Nobody else can stop or discard
  it, on their own screen or anybody else's.
* A user with no employee record is told plainly, rather than losing the time to
  a silent failure.

Where it appears
----------------
Start and Stop buttons in the task header and in the task list, plus a banner on
the form showing how long the current timer has been running.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['project', 'hr_timesheet'],
    'data': ['views/project_task_views.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
