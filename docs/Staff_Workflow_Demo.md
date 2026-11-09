# Staff workflow: short demo guide

## Start

Restart the running Streamlit app after updating the code:

```powershell
python -m streamlit run app.py
```

Existing patients stay in the same local SQLite database. The app adds new tables
and columns automatically. Use fictional demo data.

## Prepare accounts once

1. On the first launch, create an administrator with a password of your choice
   (10 or more characters). Do not put passwords in GitHub.
2. Sign out. Each staff member chooses Create account and sets their own username,
   password and requested role. As administrator, use Navigation > Staff accounts
   > Pending approvals, verify the request and approve it. There are no built-in
   demo passwords and no public administrator sign-up.
3. Sign out before switching users. A separate browser profile/private window can
   demonstrate another staff session alongside the first one.
4. At sign-in, choose the account's role: Doctor, Nurse, Receptionist,
   Administrator, or Patient. Choosing another role does not change permissions.
5. To demonstrate Patient access, first register a demo patient. The patient uses
   Create account to choose their own credentials. As administrator, open Navigation
   > Patient accounts > Pending approvals, verify identity, select the matching
   numeric patient ID and approve. Sign out, select Patient, and sign in. Only that
   patient's visits and reports appear. Patients cannot choose an ID themselves
   or use staff actions. An administrator must verify the identity before linking.

## Demonstrate the six features

1. **Reception:** sign in, choose Register patient, and register a fictional patient. The record saves
   without calling Ollama. Reception can see basic registration details, but the
   clinical report button is disabled.
2. **Doctor or Nurse:** sign in, select that patient from Patient dashboard, then
   choose Clinical review in the sidebar. Record a staff priority and reason.
   This works even if Ollama is offline.
3. **AI versus staff:** for another encounter, run triage with Ollama. Accept or
   change its suggestion. Show that the original AI report stays separate while
   the dashboard displays the latest staff decision.
4. **Reassessment:** choose Observations and reminders and enable a 1-minute
   reminder for a demo encounter. Leave this screen open. The reminder check
   refreshes every 20 seconds. Record an
   observation and select the reassessment checkbox to reset the clock. This is
   a demonstration interval, not a recommended clinical waiting time.
5. **Timeline and retention:** choose Patient timeline and load the timeline.
   Show the review and observation entries with staff names and timestamps.
   Choose Patient report to mark care completed, then use Patient dashboard to
   search Completed patients: the record and report remain available, and its
   reminder no longer appears.
6. **Audit:** sign in as administrator, choose Navigation > Audit history, and enable Show audit history. Show the
   registration, report views, staff decisions, observations and status changes.
   Disable a test staff account to demonstrate access revocation.

## What to explain honestly

- This is a local workflow prototype; these features do not establish clinical
  accuracy or make it ready for hospital deployment.
- Role names represent permissions assigned by your administrator; the app does
  not verify professional qualifications.
- Reminders require an open clinical page. There are no background notifications.
- Records from before audit logging began do not have a reconstructed activity log.
- Existing reports reopen without an AI request. A saved failed/manual visit has a
  button to try AI later, using its original intake description.
- Authentication is local to each laptop's database. Teammates do not share users
  or patient records through GitHub.
