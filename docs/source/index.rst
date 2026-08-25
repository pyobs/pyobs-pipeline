pyobs-pipeline
##############

Web-based monitoring and configuration for pyobs data reduction pipelines: monitor status, view
logs, retrigger reduction periods, and configure pipeline steps through a guided builder,
replacing SSH + manual YAML editing.

No REST API beyond one small JSON status-polling endpoint (see :doc:`architecture`) — this is a
server-rendered Django app, not a client/API split like pyobs-portal or pyobs-archive.

.. toctree::
   :maxdepth: 1

   installation
   configuration
   architecture
   development
