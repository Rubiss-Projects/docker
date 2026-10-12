@echo off
rem Monitoring-only handler: never shut down Windows or switch UPS power.
rem apcupsd records power events in its own event log.
exit /b 0
