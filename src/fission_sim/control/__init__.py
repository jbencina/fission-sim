"""Control-layer components.

The control layer sits above physics in the four-layer dependency stack
(Visualization → Control → Physics → Engine). Control modules read
physics outputs and operator inputs and produce actuator demands that
physics modules consume.

Currently holds ``PressurizerController`` and ``TavgController``. The
``RodController`` is conceptually a control component but lives in
``physics/`` for historical reasons.
"""
