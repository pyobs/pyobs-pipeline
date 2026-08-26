pyobs-pipeline
##############

Web-based monitoring and configuration for pyobs data reduction pipelines: monitor status, view
logs, retrigger reduction periods, and configure pipeline steps through a guided builder,
replacing SSH + manual YAML editing.

No REST API beyond one small JSON status-polling endpoint (see :doc:`architecture`) — this is a
server-rendered Django app, not a client/API split like pyobs-portal or pyobs-archive.

Screenshots
===========

Dashboard, with one card per site:

.. image:: _static/screenshots/dashboard.jpg
   :alt: Dashboard showing two site cards (IAG 50cm and Sutherland) with last period, next
         trigger, and input/output status, plus a table of recent reduction periods across all
         statuses.
   :width: 100%

The guided pipeline builder, introspecting a pyobs-core processor class's constructor into a
form:

.. image:: _static/screenshots/pipeline-builder.jpg
   :alt: Pipeline step editor showing Calibration and SepSourceDetection steps with their
         parameters as form fields.
   :width: 100%

A reduction period's run history, manual controls, live progress, and live-tailing log viewer:

.. image:: _static/screenshots/period-detail.jpg
   :alt: Period detail page showing Start/Stop/Reset/Restart controls and a history table of
         past runs for that date.
   :width: 100%

.. image:: _static/screenshots/period-logs.jpg
   :alt: Period detail page scrolled to the progress section (master calibrations, science
         frame count) and a live log viewer.
   :width: 100%

.. toctree::
   :maxdepth: 1

   installation
   configuration
   architecture
   development
