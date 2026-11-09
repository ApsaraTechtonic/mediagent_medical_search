import re
import sqlite3
from datetime import datetime, timedelta, timezone
import patient_store
from importlib import reload

# A running Streamlit session may still hold the storage module from before an update.
# Reload only when the required API is absent, keeping normal reruns unchanged.
if getattr(patient_store, 'WORKFLOW_SCHEMA_VERSION', 0) < 2 or not all(hasattr(patient_store, name) for name in (
    "filter_encounters", "update_care_status", "update_patient_name", "patient_code", "get_row",
)):
    reload(patient_store)
from patient_store import (
    dashboard_groups, filter_encounters, patient_code,
)
from safety_classifier import classify_patient
import html
import streamlit as st
import requests
import xml.etree.ElementTree as ET
import staff_workflow as workflow
from staff_ui import require_login, admin_panel, reminders, clinical_tools, patient_portal
from clinical_features import intake_questions, report_markdown
from voice_search import voice_input
from ui_theme import apply_theme, page_hero, patient_banner, report_cards

APP_TITLE = "MediAgent AI: Smart Healthcare Assistant"
OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b"

st.set_page_config(page_title=APP_TITLE, page_icon="🩺", layout="wide")
apply_theme()

try:
    staff_token, staff_user = require_login()
except (sqlite3.Error, OSError) as exc:
    st.error('Staff storage is unavailable. Check access to the local database. '+str(exc))
    st.stop()
is_patient = staff_user['role'] == 'Patient'
can_review = staff_user['role'] in workflow.CLINICAL
can_register = can_review or staff_user['role'] == 'Reception'

# Authenticated service boundary: callbacks use the current session on every action.
def list_encounters():
    return workflow.records(st.session_state.get('staff_token'))

def get_encounter(encounter_id):
    return workflow.record(st.session_state.get('staff_token'), encounter_id)

def create_encounter(patient, model, reference='', patient_name='', existing_patient_id=None):
    return workflow.register(st.session_state.get('staff_token'), patient, model, reference,
                             patient_name, existing_patient_id)

def finish_encounter(encounter_id, classification=None, error=None):
    return workflow.save_ai(st.session_state.get('staff_token'), encounter_id, classification, error)

def update_care_status(encounter_id, status):
    return workflow.care_status(st.session_state.get('staff_token'), encounter_id, status)

def update_patient_name(encounter_id, name):
    return workflow.patient_name(st.session_state.get('staff_token'), encounter_id, name)

pages = ['My patient records', 'ER patient triage assistant'] if is_patient else ['Patient dashboard']
if can_register:
    pages += ['Register patient']
if can_review:
    pages += ['Patient report', 'Clinical review', 'Observations and reminders', 'Patient timeline', 'Patient history']
pages += ['Medical knowledge search']
def navigate_to(destination):
    st.session_state['next_page'] = destination

if staff_user['role'] == 'Administrator':
    pages = ['Staff accounts', 'Patient accounts', 'Audit history'] + pages
if st.session_state.get('next_page') in pages:
    st.session_state['main_navigation'] = st.session_state.pop('next_page')
with staff_user['_navigation_slot']:
    page = st.radio('Navigation', pages, key='main_navigation')
if page == 'My patient records':
    patient_portal(staff_token, staff_user)
    st.stop()
if page in ('Staff accounts', 'Patient accounts', 'Audit history'):
    admin_panel(staff_token, page)
    st.stop()

page_details = {
    'ER patient triage assistant': ('Patient portal', 'ER patient triage assistant', 'Try the symptom assessment demo with a fictional case.', 'pulse'),
    'Patient dashboard': ('ER workspace', 'ER patient dashboard', 'Review the queue, open a saved report or register a new visit.', 'pulse'),
    'Register patient': ('ER workspace', 'Register patient', 'Start a new patient record or add a visit to an existing record.', 'visit'),
    'Patient report': ('ER workspace', 'Patient report', 'Review recorded intake, care status and the saved AI suggestion.', 'report'),
    'Clinical review': ('ER workspace', 'Clinical review', 'Record the clinical decision and the reasoning behind it.', 'report'),
    'Observations and reminders': ('ER workspace', 'Observations and reminders', 'Record observations and set reassessment reminders.', 'time'),
    'Patient timeline': ('ER workspace', 'Patient timeline', 'Follow recorded events in chronological order.', 'time'),
    'Patient history': ('ER workspace', 'Patient history', 'Find earlier visits and reopen their saved reports.', 'report'),
    'Medical knowledge search': ('Reference library', 'Medical Knowledge Search', 'Find MedlinePlus references and summarize them with the local model.', 'search'),
}
page_hero(*page_details[page])
st.markdown('<div class="prototype-note">Unvalidated clinical support prototype. For a possible emergency, activate local emergency procedures immediately. Use fictional demo records.</div>', unsafe_allow_html=True)

def call_ollama(messages, model, num_predict=None, response_format=None):
    try:
        payload = {"model": model, "messages": messages, "stream": False, "keep_alive": "10m"}
        if response_format is not None:
            payload["format"] = response_format
            payload["options"] = {"temperature": 0}
        if num_predict is not None:
            payload.setdefault("options", {})["num_predict"] = num_predict
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Cannot connect to Ollama at http://localhost:11434. Open Ollama and "
            "confirm the model is installed with `ollama pull qwen2.5:3b`."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("The local model timed out. Retry, or use a smaller model.") from exc

    if response.status_code == 404:
        raise RuntimeError(f"Model '{model}' was not found. Run `ollama pull {model}`.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {detail}")

    try:
        answer = response.json().get("message", {}).get("content", "").strip()
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("Ollama returned an unexpected response.") from exc
    if not answer:
        raise RuntimeError("The local model returned an empty answer. Please try again.")
    return answer

def render_review_warning(classification):
    """Display review needs independently of the model's free-text concern list."""
    if classification["immediate_emergency"]:
        st.error("**Possible immediate emergency — do not wait for this app.** "
                 "If happening now, call your local emergency number or activate your facility's emergency response.",
                 icon="🚨")
    elif classification["priority"] in ("Critical", "Urgent"):
        st.error("**Safety warning — prompt human assessment required.** "
                 "The model flagged this description for priority clinician review. "
                 "If immediate danger is possible, follow local emergency procedures.", icon="⚠️")
    elif classification["priority"] == "Unable to determine":
        st.warning("**Safety warning — human assessment and clarification required.** "
                   "There is not enough information to determine priority. This does not establish safety "
                   "or rule out an emergency. Seek qualified human assessment; if immediate danger is "
                   "possible, do not wait for this app.", icon="⚠️")
    elif classification["concerns"]:
        st.warning("**Safety concern — clinician review required.** "
                   "Review the concerns below; the model's priority does not establish safety.", icon="⚠️")


def _clean_medlineplus_text(value):
    """Decode MedlinePlus HTML snippets and remove markup for readable text."""
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.split())


def _parse_medlineplus_xml(xml_bytes, max_results=3):
    """Parse MedlinePlus XML into clean source records."""
    root = ET.fromstring(xml_bytes)
    results = []
    for doc in root.findall(".//document"):
        url = (doc.attrib.get("url") or "").strip()
        title = ""
        summary = ""
        snippet = ""
        for content in doc.findall("content"):
            name = (content.attrib.get("name") or "").lower()
            text_value = _clean_medlineplus_text("".join(content.itertext()))
            if name == "title" and text_value:
                title = text_value
            elif name == "fullsummary" and text_value and not summary:
                summary = text_value
            elif name == "snippet" and text_value and not snippet:
                snippet = text_value
        if title and url:
            results.append({"title": title, "url": url,
                            "summary": (summary or snippet)[:1800]})
        if len(results) >= max_results:
            break
    return results


def _medlineplus_query_variants(query):
    """Search concise topic keywords first; full questions are usually too restrictive."""
    variants = []
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", query.lower())
    stop_words = {
        "a", "an", "and", "are", "about", "can", "could", "do", "does", "for",
        "from", "how", "i", "in", "is", "it", "its", "me", "of", "on", "or",
        "please", "should", "someone", "tell", "that", "the", "their", "them",
        "there", "this", "to", "was", "what", "when", "where", "which", "who",
        "why", "with", "would", "you", "your", "common", "symptoms", "signs",
        "seek", "urgent", "medical", "attention", "treatment", "explain", "describe",
    }
    keywords = [word for word in words if word not in stop_words]
    if keywords:
        # Topic-first search avoids a slow, usually fruitless request for the full question.
        variants.append(" ".join(keywords[:3]))
        for word in keywords[:4]:
            if word not in variants:
                variants.append(word)
    if not variants:
        variants.append(query.strip())
    return variants


@st.cache_data(ttl=3600, show_spinner=False)
def search_medlineplus(query, max_results=3):
    """Search concise keywords first and cache successful results for one hour."""
    endpoint = "https://wsearch.nlm.nih.gov/ws/query"
    try:
        for search_term in _medlineplus_query_variants(query):
            response = requests.get(
                endpoint,
                params={"db": "healthTopics", "term": search_term, "retmax": max_results},
                timeout=8,
                headers={"User-Agent": "MediAgentAI-HackathonPrototype/1.0"},
            )
            response.raise_for_status()
            parsed = _parse_medlineplus_xml(response.content, max_results=max_results)
            if parsed:
                return parsed
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("MedlinePlus search timed out. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "Could not reach MedlinePlus. Check your internet connection and try again. "
            "No uncited answer was generated."
        ) from exc
    except ET.ParseError as exc:
        raise RuntimeError("MedlinePlus returned an unexpected response. Please try again.") from exc
    return []


KNOWLEDGE_SYSTEM = """You are a cautious medical knowledge assistant for educational reference.
Explain concepts clearly and distinguish established information from uncertainty. Keep answers concise. When the user asks about urgent-care or emergency signs, prioritize those warning signs and the appropriate action; never omit an important emergency warning merely to be brief. For medication questions, mention relevant contraindications, interactions and monitoring; do not guess doses.
Do not pretend to have searched the live web or a curated database, and do not fabricate citations.
Encourage verification against current official drug labels, reputable guidelines, local protocols,
and qualified clinicians. This is not patient-specific medical advice."""

model = DEFAULT_MODEL
if not is_patient:
    with st.sidebar:
        st.header("Local modl settings")
        model = st.text_input("Ollama model name", value=DEFAULT_MODEL).strip() or DEFAULT_MODEL
        st.caption("The model must already be downloaded in Ollama.")
        if st.button("Test local model connection", use_container_width=True):
            try:
                with st.spinner("Testing Ollama..."):
                    answer = call_ollama(
                        [{"role": "user", "content": "Reply exactly: Connection successful."}],
                        model,
                    )
                st.success(answer[:200])
            except Exception as exc:
                st.error(str(exc))


def arrival_label(value):
    return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %H:%M:%S IST")


def open_saved_encounter(encounter_id):
    st.session_state["selected_encounter"] = encounter_id
    st.session_state["next_page"] = "Patient report"
    st.session_state.pop("unsaved_report", None)


def select_patient_visit(key):
    st.session_state['selected_encounter'] = st.session_state[key]
    st.session_state.pop('unsaved_report', None)


def change_care_status(encounter_id, status):
    try:
        update_care_status(encounter_id, status)
        st.session_state["care_message"] = "Care status updated to " + status + ". The patient record and report are retained."
    except (sqlite3.Error, OSError, ValueError, PermissionError) as exc:
        st.session_state["care_error"] = "Could not update care status: " + str(exc)


def save_patient_name(encounter_id):
    try:
        update_patient_name(encounter_id, st.session_state["name_" + encounter_id])
        st.session_state["care_message"] = "Patient name saved."
    except (sqlite3.Error, OSError, ValueError, PermissionError) as exc:
        st.session_state["care_error"] = "Could not save patient name: " + str(exc)


def render_patient_rows(records):
    for record in records:
        with st.container(border=True, key='queue_row_'+record['id']):
            columns = st.columns([2, 2, 3])
            columns[0].button(patient_code(record["patient_id"]) + (" · " + record["patient_name"] if record["patient_name"] else ""), key="open_" + record["id"], use_container_width=True, disabled=not can_review, on_click=open_saved_encounter, args=(record["id"],))
            columns[0].caption(f'{record["visit_type"]} · {record["age"]} years · {record["gender"]}')
            result = record.get('review') or record["classification"]
            priority = result["priority"] if result else record["status"]
            tone = {"Critical": "critical", "Urgent": "urgent", "Non-urgent": "routine"}.get(priority, "unknown")
            if can_review:
                columns[1].markdown(f'<span class="queue-pill badge-{tone}">{html.escape(priority)}</span>',
                                    unsafe_allow_html=True)
            if record.get('review'):
                columns[1].caption('Staff decision · AI: '+(record['classification']['priority'] if record['classification'] else 'Unavailable'))
            columns[1].caption("Care: " + record["care_status"])
            columns[2].caption('Arrived ' + arrival_label(record["created_at"]))
            if record["symptoms"]:
                columns[2].write(record["symptoms"][:120] + ("…" if len(record["symptoms"]) > 120 else ""))


if page in ('Patient dashboard', 'Register patient', 'Patient report', 'Clinical review', 'Observations and reminders', 'Patient timeline', 'Patient history'):
    if can_review and page == 'Observations and reminders':
        reminders(staff_token)
    if not can_review:
        st.info('Your role can view registration details only. Clinical records are restricted to Nurse and Doctor accounts.')
    if st.session_state.get("care_message"):
        st.success(st.session_state.pop("care_message"))
    if st.session_state.get("care_error"):
        st.error(st.session_state.pop("care_error"))
    if st.session_state.get('report_save_error'):
        st.error(st.session_state.pop('report_save_error'))
    run_triage = False
    storage_error = None
    try:
        records = list_encounters()
    except (sqlite3.Error, OSError) as exc:
        records = []
        storage_error = str(exc)
        st.error("Patient storage is unavailable. No new submission can be saved. " + storage_error)

    if page == 'Register patient':
        registration = st.radio("Visit registration", ["New patient", "Returning patient"], horizontal=True, key="registration_type")
        existing = None
        if registration == "Returning patient":
            by_patient = {r["patient_id"]: r for r in records}
            if by_patient:
                chosen = st.selectbox("Select existing patient", list(by_patient), key="existing_patient",
                                     format_func=lambda pid: patient_code(pid) + " · " + (by_patient[pid]["patient_name"] or "Unnamed") + " · " + arrival_label(by_patient[pid]["created_at"]))
                existing = by_patient[chosen]
                st.caption("A new visit will be saved under this patient ID; previous reports remain unchanged.")
            else:
                st.info("No existing patients yet. Register a new patient first.")
        with st.form("triage_form"):
            patient_name = st.text_input("Patient name (optional)", value=existing["patient_name"] if existing else "", key="registration_name_" + (str(existing["patient_id"]) if existing else "new"), max_chars=120, placeholder="Demo patient name for searching later")
            reference = st.text_input("Patient reference (optional)", max_chars=60,
                                      placeholder="Optional bed code or note; the patient ID is generated automatically")
            st.caption("Each submission creates a separate encounter. Use fictional names in this local prototype. Names are stored for search and are not sent to the model.")
            col1, col2 = st.columns(2)
            with col1:
                age = st.number_input("Patient age (years)", min_value=0, max_value=120, value=45, step=1)
            with col2:
                gender = st.selectbox("Patient gender", ["Not specified", "Female", "Male", "Intersex", "Another identity"])
            symptoms = st.text_area("Symptoms / vitals / relevant context",
                                    placeholder="Describe symptoms, onset, severity, vital signs, and relevant history if known.",
                                    height=170, max_chars=8000)
            intake = intake_questions()
            manual_only = st.checkbox('Save for manual assessment (skip AI)', value=not can_review,
                                      disabled=not can_review)
            run_triage = st.form_submit_button("Run Triage Analysis" if can_review else "Register for clinical assessment", type="primary", use_container_width=True,
                                              disabled=not can_register or storage_error is not None or (registration == "Returning patient" and existing is None))

    review_alert = st.empty()
    if run_triage:
        if not symptoms.strip():
            st.warning("Please enter symptoms or relevant clinical information first.")
        else:
            patient = {"age": age, "gender": gender, "symptoms": symptoms.strip(), 'intake': intake}
            encounter_id = None
            classification = None
            st.session_state.pop("unsaved_report", None)
            try:
                encounter_id = create_encounter(patient, model, reference, patient_name,
                                                existing_patient_id=existing["patient_id"] if existing else None)
                st.session_state["selected_encounter"] = encounter_id
                if manual_only or not can_review:
                    st.info('Patient saved for manual assessment. No AI request was made.')
                else:
                    with st.spinner("Classifying patient context with Ollama..."):
                        classification = classify_patient(patient, model, call_ollama)
                    with review_alert.container():
                        render_review_warning(classification)
                    finish_encounter(encounter_id, classification=classification)
            except Exception as exc:
                if classification is not None:
                    # Preserve a successful model report if saving it fails.
                    st.session_state["unsaved_report"] = dict(patient, classification=classification)
                    st.session_state['report_save_error'] = "The report was generated but could not be saved. Keep this page open. " + str(exc)
                elif encounter_id is not None:
                    try:
                        finish_encounter(encounter_id, error=str(exc))
                    except (sqlite3.Error, OSError):
                        st.error("Could not save the classification failure. The encounter may still appear as pending.")
                else:
                    st.error("Could not create a patient record; the model was not called. " + str(exc))
            try:
                records = list_encounters()
            except (sqlite3.Error, OSError):
                st.error("Could not refresh saved patients. Try Refresh dashboard.")

    if run_triage and encounter_id is not None:
        st.session_state['next_page'] = 'Patient report' if can_review else 'Patient dashboard'
        st.rerun()

    if page == 'Patient dashboard':
        with st.container(border=True):
            actions = st.columns([1, 1, 2])
            if can_register:
                actions[0].button('Register a patient', on_click=navigate_to, args=('Register patient',), type='primary')
            actions[1 if can_register else 0].button("Refresh dashboard", key="refresh_dashboard")
            search = st.text_input("Search patients by name or reference", key="patient_search", placeholder="Patient name or numeric patient ID, e.g. 10001")
            view = st.radio("Patient records", ["All patients", "Active patients", "Completed patients"], horizontal=True, key="patient_view")
        visible = filter_encounters(records, search, view)
        completed = sorted((r for r in visible if r["care_status"] == "Completed"),
                           key=lambda r: r["completed_at"] or r["created_at"], reverse=True)
        classified, assessment = dashboard_groups(visible)
        with st.container(key='dashboard_stats'):
            metrics = [('Matching visits', len(visible))]
            if can_review:
                for priority in ('Critical', 'Urgent', 'Non-urgent'):
                    metrics.append((priority, sum((r.get('review') or r["classification"])["priority"] == priority
                                                  for r in classified)))
                metrics.append(('Needs assessment', len(assessment)))
            metrics.append(('Care completed', len(completed)))
            for column, (label, count) in zip(st.columns(len(metrics)), metrics):
                column.metric(label, count)
        if assessment and can_review:
            st.warning("Patients need human assessment: classification is uncertain, pending, or failed. "
                       "They are shown separately and must not be treated as a lower-priority queue.", icon="⚠️")
            with st.expander("Needs assessment (" + str(len(assessment)) + ")", expanded=True):
                render_patient_rows(assessment)
        if classified:
            st.write("**Patients sorted by recorded staff priority, or AI suggestion when unreviewed**")
            st.caption("Critical → Urgent → Non-urgent; immediate-emergency flags first within a priority, then earliest arrival. "
                       "This display order is not a validated clinical queue or a decision that someone can wait.")
            render_patient_rows(classified)
        if not can_review and visible:
            render_patient_rows([r for r in visible if r['care_status'] != 'Completed'])
        if completed:
            st.write("**Completed care — retained patient records**")
            render_patient_rows(completed)
        if records and not visible:
            st.info("No patients match this name/reference and care-status filter.")
        if not records and not storage_error:
            st.info("No patients saved yet. Choose Register patient from the sidebar.")

    if page in ('Patient report', 'Clinical review', 'Observations and reminders', 'Patient timeline', 'Patient history') and records:
        ids = [r['id'] for r in records]
        by_id = {r['id']:r for r in records}
        current = st.session_state.get('selected_encounter')
        picker = 'visit_selector_'+page
        st.session_state[picker] = current if current in ids else ids[-1]
        with st.sidebar.expander('Switch patient visit'):
            chosen = st.selectbox('Selected patient visit', ids, index=None,
                format_func=lambda eid:patient_code(by_id[eid]['patient_id'])+' - '+(by_id[eid]['patient_name'] or 'Unnamed')+' - '+arrival_label(by_id[eid]['created_at']),
                key=picker, on_change=select_patient_visit, args=(picker,))
        st.session_state['selected_encounter'] = chosen
    selected_id = st.session_state.get('selected_encounter')
    selected = None
    if selected_id and can_review and page not in ('Patient dashboard', 'Register patient'):
        try:
            selected = get_encounter(selected_id)
        except (sqlite3.Error, OSError, PermissionError):
            st.error("Could not load the selected patient's saved report.")
    unsaved = st.session_state.get("unsaved_report")
    if can_review and page not in ('Patient dashboard', 'Register patient') and (selected or unsaved):
        report = unsaved or selected
        if page == 'Patient report':
            current_review = next((r.get('review') for r in records if selected and r['id']==selected['id']), None)
            st.markdown(patient_banner(report, current_review), unsafe_allow_html=True)
        if selected:
            if page != 'Patient report':
                st.write("**Patient ID:** " + patient_code(selected["patient_id"]))
                st.write("**Visit type:** " + selected["visit_type"])
                if selected["reference"] and selected["reference"] != selected["visit_code"]:
                    st.write("**Bed / reference note:** " + selected["reference"])
                st.write("**Patient name:** " + (selected["patient_name"] or "Not recorded"))
                st.write("**Care status:** " + selected["care_status"])
                if selected["completed_at"]:
                    st.caption("Care completed: " + arrival_label(selected["completed_at"]))
                st.caption("Care status is recorded manually; generating a report does not mark the patient as attended.")
            if page != 'Patient report':
                st.caption("Arrived: " + arrival_label(selected["created_at"]) + " · Model: " + selected["model"])
            if page in ('Patient report', 'Patient history'):
                visits = sorted([r for r in records if r['patient_id']==selected['patient_id']], key=lambda r:r['created_at'], reverse=True)
                with st.expander('Saved visits ('+str(len(visits))+')', expanded=page=='Patient history'):
                    st.caption(str(len(visits))+' saved visit(s) for this patient. Select an earlier visit to open its original report.')
                    for visit in visits:
                        if page == 'Patient history' or len(visits)>1:
                            st.button('Open '+visit['visit_type']+' · '+arrival_label(visit['created_at'])+' · '+visit['care_status'],
                                      key='visit_report_'+visit['id'], on_click=open_saved_encounter, args=(visit['id'],))
                if page == 'Patient history':
                    st.subheader('Recorded history by visit')
                    for visit in visits:
                        with st.expander(arrival_label(visit['created_at'])+' · '+visit['visit_type'], expanded=visit['id']==selected['id']):
                            st.write('Reported context: '+visit['symptoms'])
                            st.write('Care status: '+visit['care_status'])
                            st.json(visit.get('intake') or {'History':'No additional intake recorded on this visit.'})
                            if visit.get('review'):
                                st.write('Staff priority: '+visit['review']['priority'])
                            st.write('AI priority: '+(visit['classification']['priority'] if visit['classification'] else 'Unavailable'))
            if page == 'Patient timeline':
                history = [r for r in records if r["patient_id"] == selected["patient_id"]]
                with st.expander("Visit history (" + str(len(history)) + ")"):
                    for visit in reversed(history):
                        st.button(arrival_label(visit["created_at"]) + " · " + visit["care_status"],
                                  key="history_" + visit["id"], on_click=open_saved_encounter, args=(visit["id"],))
            if page not in ('Patient report', 'Patient history'):
                clinical_tools(staff_token, selected, records, arrival_label, section=page)
        if page == 'Patient report':
            latest_review = next((r.get('review') for r in records if selected and r['id']==selected['id']), None)
            if latest_review:
                st.info('Recorded staff decision: '+latest_review['priority']+' · '+latest_review['reason'])
            if unsaved:
                st.warning("This generated report has not been saved to the database.")
            classification = report["classification"]
            if classification is None:
                if report["error"]:
                    st.error(report["error"])
                st.warning("Classification unavailable. No safety conclusion was produced. "
                           "Seek human assessment; do not wait for this app if an emergency is possible. "
                           "A pending record may represent a running or interrupted request.")
                if selected and st.button('Try AI classification for this saved visit', key='retry_ai_'+selected['id']):
                    try:
                        patient = {k: selected[k] for k in ('age', 'gender', 'symptoms', 'intake')}
                        with st.spinner('Classifying the saved context with Ollama...'):
                            result = classify_patient(patient, model, call_ollama)
                        finish_encounter(selected['id'], classification=result)
                        st.rerun()
                    except Exception as exc:
                        finish_encounter(selected['id'], error=str(exc))
                        st.error('AI unavailable. Manual assessment remains available. '+str(exc))
            else:
                st.subheader("Original AI suggestion (not the staff decision)")
                st.write("**Provisional priority:** " + classification["priority"])
                # Keep the alert next to its report rather than in the earlier page placeholder.
                render_review_warning(classification)
                report_cards(report, latest_review)
                st.write("**AI-listed concerns**")
                for concern in classification["concerns"]:
                    if classification['priority'] == 'Critical' or classification['immediate_emergency']:
                        st.error(concern, icon='🚨')
                    else:
                        st.warning(concern)
                for context in classification["historical_context"]:
                    st.info("Historical context: " + context)
                st.caption("Saved model-generated report for clinician review. Opening a report does not call Ollama again. "
                           "This is not validated triage or a suicide-risk assessment.")
            if classification is None:
                report_cards(report, latest_review)
            if selected:
                actions = st.columns(3)
                actions[0].button("Start care", key="start_care", type="primary", disabled=selected["care_status"] != "Waiting",
                                  on_click=change_care_status, args=(selected["id"], "In care"))
                actions[1].button("Mark care completed", key="complete_care", disabled=selected["care_status"] == "Completed",
                                  on_click=change_care_status, args=(selected["id"], "Completed"))
                actions[2].button("Reopen encounter", key="reopen_care", disabled=selected["care_status"] != "Completed",
                                  on_click=change_care_status, args=(selected["id"], "Waiting"))
                with st.expander("Add or edit patient name"):
                    with st.form("patient_name_form_" + selected["id"]):
                        st.text_input("Patient name", value=selected["patient_name"], max_chars=120,
                                      key="name_" + selected["id"])
                        st.form_submit_button("Save patient name", on_click=save_patient_name, args=(selected["id"],))
            st.download_button('Download structured report', report_markdown(report, latest_review),
                               file_name='MediAgent_patient_'+str(report.get('patient_id','unsaved'))+'_report.md', mime='text/markdown')
            with st.expander('All recorded intake fields and visit metadata'):
                st.caption('Arrived: '+arrival_label(report['created_at']) if report.get('created_at') else 'Not saved')
                if report.get('intake'):
                    st.table([{'Field':k,'Recorded information':v} for k,v in report['intake'].items()])
                else:
                    st.caption('No additional intake was recorded for this visit. Older reports remain available.')

    if page not in ('Patient dashboard', 'Register patient') and not selected and not unsaved:
        st.info('No patient visit is selected. Register a patient or choose a patient from the dashboard.')


if page == 'ER patient triage assistant':
    st.warning('For a possible emergency, seek emergency help now. Use the emergency guide in the sidebar if you need contact information.')
    st.caption('Use fictional symptoms. This check does not save a visit or notify the ER team.')
    with st.form('patient_triage'):
        age = st.number_input('Patient age (years)', min_value=0, max_value=120, value=None, step=1)
        symptoms = st.text_area('Symptoms and relevant context', max_chars=8000,
                                placeholder='Describe what is happening and when it started.')
        run_check = st.form_submit_button('Check symptoms', type='primary')
    if run_check:
        if not symptoms.strip():
            st.warning('Enter symptoms or relevant context to run the check.')
        else:
            try:
                with st.spinner('Checking symptoms with the local model…'):
                    result = classify_patient({'age': age, 'symptoms': symptoms.strip()}, model, call_ollama)
            except (RuntimeError, requests.RequestException):
                st.warning('The symptom check is unavailable. Contact a qualified healthcare professional for assessment.')
            else:
                st.subheader('Symptom check result')
                render_review_warning(result)
                st.info('A qualified healthcare professional can assess these symptoms. This demo cannot rule out an emergency.')

if page == 'Medical knowledge search':
    st.caption("MedlinePlus is provided by the U.S. National Library of Medicine. Internet access is required to retrieve references.")
    if is_patient:
        st.caption('Ask a general health question. Leave out names, patient IDs and other identifying details.')
    st.write('**Try a reference topic**')
    for column, topic in zip(st.columns(3), ('Asthma', 'Migraine', 'Blood pressure')):
        column.button(topic, key='reference_topic_'+topic, on_click=st.session_state.update,
                      kwargs={'knowledge_question': topic})
    voice_input()
    with st.form("knowledge_form"):
        question = st.text_area(
            "Medical / drug reference question",
            placeholder="Enter a medical or medication reference question...",
            height=150,
            max_chars=6000,
            key='knowledge_question',
        )
        run_knowledge = st.form_submit_button(
            "Search Medical Database", type="primary", use_container_width=True
        )
    if run_knowledge:
        if not question.strip():
            st.warning("Please enter a medical or drug reference question.")
        else:
            try:
                with st.spinner("Searching MedlinePlus for relevant health references..."):
                    sources = search_medlineplus(question.strip(), max_results=2)

                st.session_state["knowledge_sources"] = sources
                if not sources:
                    st.warning(
                        "No MedlinePlus health-topic results were found for this query. "
                        "Try simpler keywords or verify the topic using an official drug label "
                        "or your institution's approved reference. No AI answer was generated "
                        "because no source material was retrieved."
                    )
                    st.session_state["knowledge_result"] = None
                else:
                    context_parts = []
                    for i, item in enumerate(sources, start=1):
                        context_parts.append(
                            f"SOURCE {i}\nTitle: {item['title']}\nURL: {item['url']}\n"
                            f"Retrieved summary: {(item['summary'] or '[No summary snippet returned]')[:500]}"
                        )
                    grounded_prompt = (
                        "Give a concise answer (about 70-100 words) to the user's medical reference question using ONLY the retrieved "
                        "source material below. Prefer short paragraphs and avoid repeating details. If the sources do not answer the question, say "
                        "what is missing and do not fill gaps from memory. Distinguish general "
                        "education from patient-specific advice. For medication questions, do not "
                        "invent doses; explain that current official product labeling and a "
                        "qualified clinician/pharmacist should be consulted for dosing, interactions, "
                        "contraindications, pregnancy considerations, and monitoring. Do not create "
                        "citations or URLs. Cite only the supplied source numbers, e.g. [1], when "
                        "the source directly supports the statement. Mention uncertainty clearly.\n\n"
                        f"USER QUESTION:\n{question.strip()}\n\n"
                        "RETRIEVED MEDLINEPLUS SOURCES:\n" + "\n\n".join(context_parts)
                    )
                    with st.spinner("Summarizing retrieved sources with the local model..."):
                        st.session_state["knowledge_result"] = call_ollama(
                            [{"role": "system", "content": KNOWLEDGE_SYSTEM},
                             {"role": "user", "content": grounded_prompt}],
                            model,
                            num_predict=125,
                        )
            except Exception as exc:
                st.session_state["knowledge_result"] = None
                st.session_state["knowledge_sources"] = []
                st.error(str(exc))

    if st.session_state.get("knowledge_result"):
        with st.container(border=True, key='reference_answer'):
            st.subheader("Reference answer")
            st.markdown(st.session_state["knowledge_result"])
            st.caption(
                "This is an AI-generated summary of retrieved source snippets, not patient-specific "
                "medical advice. Check the full source and current local guidance."
            )
        sources = st.session_state.get("knowledge_sources", [])
        if sources:
            st.subheader("Retrieved sources")
            for i, item in enumerate(sources, start=1):
                with st.container(border=True):
                    st.markdown(f"**[{i}] [{item['title']}]({item['url']})**")
                    if item["summary"]:
                        st.caption(item["summary"][:500])


st.caption("MediAgent AI · Local prototype · No OpenAI API used.")
