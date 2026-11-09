"""Streamlit staff screens. Authorization is enforced again by staff_workflow."""
import html
import json
import re
import sqlite3

import streamlit as st
import staff_workflow as workflow
from clinical_features import emergency_information, report_markdown
from ui_theme import page_hero, session_card, sidebar_brand


def clear_session():
    for key in list(st.session_state):
        del st.session_state[key]


def require_login():
    with st.sidebar:
        sidebar_brand()
        navigation_slot = st.container()
    with st.sidebar:
        st.markdown('**India emergency: [112](tel:112)**')
        st.caption('Outside India, use your local emergency number.')
        if st.button('Open emergency guide'):
            st.session_state['public_emergency'] = True
    if st.session_state.get('public_emergency'):
        if st.button('Back to MediAgent'):
            st.session_state.pop('public_emergency', None)
            st.rerun()
        emergency_information()
        st.stop()
    workflow.initialize()
    token = st.session_state.get('staff_token')
    if token:
        try:
            user = workflow.current_user(token)
        except PermissionError:
            clear_session()
            st.warning('Your session has expired or access has changed. Please sign in.')
        else:
            with st.sidebar:
                session_card(user)
                with st.expander('Change my password'):
                    with st.form('own_password'):
                        old = st.text_input('Current password', type='password')
                        new = st.text_input('New password (at least 10 characters)', type='password')
                        confirm = st.text_input('Confirm new password', type='password')
                        if st.form_submit_button('Change my password'):
                            try:
                                if new != confirm:
                                    raise ValueError('Passwords do not match.')
                                workflow.change_own_password(token, old, new)
                                clear_session()
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                if st.button('Sign out'):
                    workflow.logout(token)
                    clear_session()
                    st.rerun()
            user['_navigation_slot'] = navigation_slot
            return token, user
    with st.container(key='auth_workspace'):
        intro, access_panel = st.columns([2, 3], gap='medium')
        with intro:
            page_hero('Local demo · Use fictional records', 'Welcome to MediAgent',
                      'One workspace for patient visits, clinical review and medical reference search.', 'pulse')
        with access_panel:
            with st.container(border=True, key='auth_panel'):
                _account_entry()
    st.stop()


def _account_entry():
    if workflow.needs_setup():
        st.info('First-time setup: create the initial administrator. Other users then choose Create account and set their own credentials.')
        with st.form('initial_admin'):
            name = st.text_input('Administrator display name')
            username = st.text_input('Administrator username')
            password = st.text_input('Administrator password (at least 10 characters)', type='password')
            confirm = st.text_input('Confirm password', type='password')
            if st.form_submit_button('Create administrator'):
                try:
                    if password != confirm:
                        raise ValueError('Passwords do not match.')
                    workflow.bootstrap_admin(username, name, password)
                    st.success('Administrator created. Sign in with this account.')
                    st.rerun()
                except (ValueError, sqlite3.Error) as exc:
                    st.error(str(exc))
    else:
        with st.container(key='auth_access'):
            access = st.radio('Account access', ['Log in', 'Create account'], horizontal=True, key='account_access')
        if access == 'Create account':
            st.subheader('Create your account')
            st.caption('Choose your own username and password. Access becomes available after identity verification and approval.')
            with st.form('public_signup'):
                display_name = st.text_input('Your name')
                username = st.text_input('Choose a username')
                roles = {'Patient':'Patient', 'Doctor':'Doctor', 'Nurse':'Nurse', 'Receptionist':'Reception'}
                role = st.selectbox('Requested account role', list(roles))
                password = st.text_input('Choose a password (at least 10 characters)', type='password')
                confirm = st.text_input('Confirm your password', type='password')
                if st.form_submit_button('Submit sign-up'):
                    try:
                        if password != confirm:
                            raise ValueError('Passwords do not match.')
                        workflow.sign_up(username, display_name, roles[role], password)
                        st.success('Account created. Remember your username: '+username.strip().casefold()+
                                   '. Approval is pending. After approval, choose Log in and use your own password.')
                    except sqlite3.IntegrityError:
                        st.error('That username is already taken. Choose another username.')
                    except ValueError as exc:
                        st.error(str(exc))
            return
        options = {'Doctor':'Doctor', 'Nurse':'Nurse', 'Receptionist':'Reception',
                   'Administrator':'Administrator', 'Patient':'Patient'}
        selected = st.radio('Sign in as', list(options), horizontal=True, key='login_role')
        descriptions = {
            'Doctor':'Review patients, record clinical decisions and manage care.',
            'Nurse':'Review patients, record assessments and configure reassessment reminders.',
            'Receptionist':'Register patients and view basic registration details.',
            'Administrator':'Manage staff and patient accounts, access permissions and audit history.',
            'Patient':'Sign in after your account is approved. Visit reports appear once an administrator links your verified patient record.',
        }
        st.info(descriptions[selected])
        st.caption('Your account must have the selected role. Selecting a role does not grant extra permissions.')
        with st.form('staff_login'):
            username = st.text_input('Username')
            password = st.text_input('Password', type='password')
            if st.form_submit_button('Sign in', type='primary'):
                try:
                    token = workflow.login(username, password, expected_role=options[selected])
                    clear_session()
                    st.session_state['staff_token'] = token
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def admin_panel(token, page='Staff accounts'):
    if page == 'Audit history':
        page_hero('Access centre', page, 'Review recent account and patient record activity.', 'time')
        st.caption('Latest 250 events, newest first. Times are UTC. Audit details may contain demo clinical information.')
        if st.checkbox('Show audit history'):
            events = workflow.audit(token)
            st.dataframe(events, hide_index=True, use_container_width=True)
        return

    patient_page = page == 'Patient accounts'
    accounts = [a for a in workflow.list_staff(token) if (a['role'] == 'Patient') == patient_page]
    pending = [a for a in accounts if a['approval_state'] == 'Pending']
    approved = [a for a in accounts if a['approval_state'] == 'Approved']
    section = 'patient' if patient_page else 'staff'
    description = ('Review portal sign-ups and link them to registered patient records.' if patient_page
                   else 'Review staff sign-ups and manage access to the workspace.')
    st.markdown(f'''
        <div class="account-hero">
            <div><span class="account-eyebrow">MediAgent / Access centre</span>
                <h1>{page}</h1><p>{description}</p>
            </div>
            <div class="account-counts">
                <div><strong>{len(pending)}</strong><span>Awaiting review</span></div>
                <div><strong>{len(approved)}</strong><span>Approved</span></div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    message = st.session_state.pop('account_notice_'+section, None)
    if message:
        st.success(message)
    with st.container(key='account_switch'):
        action = st.radio('Account action', ['Pending approvals', 'Manage accounts'], horizontal=True,
                          label_visibility='collapsed', key='account_action_'+page)
    reviewing = action == 'Pending approvals'
    visible_accounts = pending if reviewing else approved
    if not visible_accounts:
        with st.container(border=True, key='account_empty'):
            st.subheader('You’re all caught up' if reviewing else 'No approved accounts yet')
            st.caption('New sign-ups will appear here for review.' if reviewing
                       else 'Approved accounts will appear here so you can manage their access.')
        return

    with st.container(key='account_workspace'):
        queue, detail = st.columns([2, 3], gap='medium')
        with queue:
            with st.container(border=True, key='account_queue'):
                st.subheader('Review queue' if reviewing else 'Account directory')
                mode = f'{section}_{reviewing}'
                query = st.text_input('Find an account', placeholder='Search by name or username',
                                      key='account_search_'+mode).strip().casefold()
                matches = {a['id']: a for a in visible_accounts if
                           query in a['display_name'].casefold() or query in a['username'].casefold()}
                if not matches:
                    st.info('No accounts match that search.')
                    return
                queue_options = st.container(height=320, border=False) if len(matches) > 6 else st.container()
                with queue_options:
                    account_id = st.radio('Select an account', list(matches),
                                          format_func=lambda uid: _account_label(matches[uid]),
                                          key='account_choice_'+mode)
                account = matches[account_id]
        with detail:
            with st.container(border=True, key='account_detail'):
                _account_details(token, section, account, reviewing)


def _account_label(account):
    label = f"{account['display_name']} · @{account['username']}"
    return re.sub(r'([\\`*_\[\]~!$<>])', r'\\\1', ' '.join(label.split()))


def _select_patient_record(token, key):
    patients = {record['patient_id']: record for record in workflow.records(token)}
    if not patients:
        st.info('No patient records are available to link yet.')
        return None
    return st.selectbox('Verified patient ID', list(patients), index=None, key=key,
                        placeholder='Search by patient name or ID',
                        format_func=lambda pid: f"{pid} · {patients[pid]['patient_name'] or 'Unnamed'}")


def _account_details(token, section, account, reviewing):
    name = html.escape(account['display_name'])
    username = html.escape(account['username'])
    role = html.escape(account['role'])
    status = 'Pending' if reviewing else ('Enabled' if account['active'] else 'Disabled')
    initial = html.escape(account['display_name'][:1].upper())
    st.markdown(f'''
        <div class="account-identity">
            <span class="account-avatar" aria-hidden="true">{initial}</span>
            <div><span class="account-eyebrow">{'Reviewing sign-up' if reviewing else 'Account access'}</span>
                <strong>{name}</strong><small>@{username} · {role}</small>
            </div>
            <span class="account-status account-status-{status.lower()}">{status}</span>
        </div>
        ''', unsafe_allow_html=True)
    account_id = account['id']
    if reviewing:
        link_now = False
        if section == 'patient':
            approval = st.radio('Patient record', ['Approve without linking', 'Link an existing record'],
                                key=f'approve_mode_{account_id}')
            link_now = approval == 'Link an existing record'
            st.caption('If this patient has never registered a visit, approve their login now. '
                       'You can link a verified record later under Manage accounts.')
        with st.form(f'approve_signup_{account_id}', border=False):
            patient_id = _select_patient_record(token, f'approve_patient_{account_id}') if link_now else None
            st.write('**Verify access**')
            verified = st.checkbox('I have verified this person and their requested access',
                                   key=f'approve_verified_{account_id}')
            if not st.form_submit_button('Approve account', type='primary'):
                return
            try:
                if not verified:
                    raise ValueError('Verify identity and access before approval.')
                workflow.approve_account(token, account_id, patient_id,
                                         allow_unlinked=section == 'patient' and not link_now)
            except ValueError as exc:
                st.error(str(exc))
                return
            message = 'Account approved. The user can now sign in.'
    else:
        if section == 'patient':
            st.caption(f"Linked patient ID: {account['patient_id'] or 'Not linked'}")
            if account['patient_id'] is None:
                with st.expander('Link an existing patient record'):
                    with st.form(f'link_patient_{account_id}'):
                        patient_id = _select_patient_record(token, f'manage_patient_{account_id}')
                        verified = st.checkbox('I have verified this record belongs to this person')
                        if st.form_submit_button('Link patient record'):
                            try:
                                if not verified:
                                    raise ValueError('Verify the patient record before linking it.')
                                workflow.link_patient_account(token, account_id, patient_id)
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                st.session_state['account_notice_'+section] = 'Patient record linked.'
                                st.rerun()
            else:
                with st.expander('Correct a patient record link'):
                    st.caption('Returning this account to review removes its record link and signs the user out. '
                               'Verify the correct patient ID in Pending approvals before restoring access.')
                    if st.button('Remove link and return to review', key=f'review_link_{account_id}'):
                        try:
                            workflow.return_patient_account_to_review(token, account_id, account['patient_id'])
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state['account_notice_'+section] = 'Patient link removed. Review the account in Pending approvals.'
                            st.rerun()
        with st.form(f'manage_account_{account_id}', border=False):
            active = st.checkbox('Account enabled', value=bool(account['active']))
            if not st.form_submit_button('Update account access', type='primary'):
                return
            try:
                workflow.set_staff_active(token, account_id, active)
            except ValueError as exc:
                st.error(str(exc))
                return
            message = 'Access updated. Existing sessions for that account were revoked.'
    st.session_state['account_notice_'+section] = message
    st.rerun()



def patient_portal(token, user):
    page_hero('Patient portal', 'My patient records', 'Open a visit to read or download its report.', 'report')
    st.caption('Signed in as '+user['display_name']+'. This portal shows only records linked to your account.')
    st.warning('Hackathon prototype: AI suggestions are unvalidated. Contact your care team for assessment; '
               'for a possible emergency, follow local emergency procedures.')
    if user['patient_id'] is None:
        st.info('No patient record is linked to your account yet. An administrator can link it after registration.')
        return
    try:
        reports = workflow.patient_reports(token)
    except PermissionError as exc:
        st.error(str(exc))
        st.stop()
    st.write('**Patient ID:** '+str(user['patient_id']))
    if not reports:
        st.info('No visits are available for your account yet.')
    for report in reports:
        with st.expander(report['created_at']+' · '+report['care_status'], expanded=len(reports)==1):
            st.download_button('Download this visit report', report_markdown(report, report.get('review')),
                               file_name='MediAgent_patient_'+str(report['patient_id'])+'_report.md',
                               mime='text/markdown', key='download_patient_'+report['id'])
            st.write('**Name:** '+(report['patient_name'] or 'Not recorded'))
            st.write('**Visit:** '+report['visit_type'])
            st.write('**Recorded symptoms / context:**')
            st.write(report['symptoms'])
            if report.get('intake'):
                st.write('**Recorded intake and history for this visit**')
                st.table([{'Field':k,'Recorded information':v} for k,v in report['intake'].items()])
            if report['review']:
                st.subheader('Recorded clinical decision')
                st.write('Priority: '+report['review']['priority'])
                st.write(report['review']['reason'])
            else:
                st.info('No staff clinical decision is recorded for this visit yet.')
            if report['classification']:
                st.subheader('AI suggestion for clinician review')
                st.write('Suggested priority: '+report['classification']['priority'])
                st.write(report['classification']['reasoning'])
                st.write('Uncertainty: '+report['classification']['uncertainty'])
            else:
                st.info('An AI report is not available for this visit. Staff can continue assessment manually.')


@st.fragment(run_every='20s')
def reminders(token):
    try:
        items = workflow.due_records(workflow.records(token))
        if items:
            st.warning(f'{len(items)} active encounter(s) have a staff-configured reassessment reminder due. '
                       'These are workflow reminders, not clinical waiting-time recommendations.')
            for r in items:
                st.write(f"Patient {r['patient_id']} · {r['patient_name'] or 'Unnamed'} · due {r['due_at']}")
                if st.button('Open for reassessment', key='due_'+r['id']):
                    st.session_state['selected_encounter'] = r['id']
                    st.session_state['next_page'] = 'Patient report'
                    st.session_state.pop('unsaved_report', None)
                    st.rerun()
        st.caption('Reminder check refreshes every 20 seconds while this page is open. No background notification is sent.')
    except PermissionError:
        st.warning('Session expired. Refresh and sign in again.')
    except (sqlite3.Error, OSError):
        st.error('Reassessment reminders are unavailable while patient storage is offline.')


def clinical_tools(token, selected, records, format_time, section='Clinical review'):
    encounter_id = selected['id']
    review = next((r.get('review') for r in records if r['id']==encounter_id), None)
    if section == 'Clinical review':
        st.subheader('Staff clinical review')
        st.caption('The original AI report is on the Patient report screen. A staff decision is stored separately with its author and reason.')
        if review:
            if review['priority'] in ('Critical', 'Urgent'):
                st.error('Recorded staff priority: '+review['priority'])
            elif review['priority'] == 'Unable to determine':
                st.warning('Recorded staff priority: Unable to determine. Further assessment is needed.')
            else:
                st.info('Recorded staff priority: '+review['priority'])
            st.write(review['decision']+' · '+review['actor_name']+' ('+review['actor_role']+') · '+format_time(review['created_at']))
            st.write('Reason: '+review['reason'])
        else:
            st.info('No staff clinical decision recorded for this visit yet.')
        with st.form('clinical_review_'+encounter_id):
            decisions = ['Record clinician decision']
            if selected['classification']:
                decisions.insert(0, 'Accept AI suggestion')
            decision = st.selectbox('Review action', decisions)
            priority = st.selectbox('Staff-assessed priority', workflow.PRIORITIES)
            reason = st.text_area('Reason for decision / assessment notes', max_chars=4000)
            st.caption('Accept AI suggestion uses the saved model priority. A manual decision uses the selected staff priority.')
            if st.form_submit_button('Save clinical review'):
                try:
                    value = selected['classification']['priority'] if decision=='Accept AI suggestion' else priority
                    workflow.review(token, encounter_id, decision, value, reason)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    if section == 'Observations and reminders':
        st.write('Arrived: '+format_time(selected['created_at']))
        st.write('Last assessed: '+(format_time(selected['last_reviewed_at']) if selected.get('last_reviewed_at') else 'Not recorded'))
        with st.form('observation_'+encounter_id):
            text = st.text_area('New observation / recorded vitals', max_chars=4000)
            assessed = st.checkbox('I reassessed this patient (reset the reminder clock)')
            if st.form_submit_button('Save observation'):
                try:
                    workflow.observation(token, encounter_id, text, assessed)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with st.form('reminder_'+encounter_id):
            enabled = st.checkbox('Enable reassessment reminder', value=bool(selected.get('review_interval_minutes')))
            minutes = st.number_input('Staff-selected interval in minutes', min_value=1, max_value=1440,
                                      value=selected.get('review_interval_minutes') or 30, step=1)
            st.caption('No interval is applied until saved. Due time is arrival or last assessment plus the interval. '
                       'Completed encounters never trigger reminders.')
            if st.form_submit_button('Save reminder setting'):
                workflow.set_reminder(token, encounter_id, int(minutes) if enabled else None)
                st.rerun()
    if section == 'Patient timeline':
        if st.checkbox('Load patient timeline', key='timeline_'+encounter_id):
            for event in workflow.timeline(token, selected['patient_id']):
                st.write('**'+format_time(event['occurred_at'])+' · '+event['action']+'**')
                st.caption(event['actor_name']+' · '+event['actor_role'])
                details = json.loads(event['details'])
                if details:
                    st.json(details)
