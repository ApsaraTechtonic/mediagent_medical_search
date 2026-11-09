"""Presentation only: reusable styles and escaped patient-summary markup."""
import html
import streamlit as st


def apply_theme():
    st.markdown('''<style>
    :root {--ink:#17324d;--teal:#087f8c;}
    .stApp {background:radial-gradient(ellipse at 80% 0%,#e1efed 0%,transparent 44%),#f3f7fa;
      color:var(--ink);font-family:'Segoe UI',sans-serif;}
    .block-container {padding-top:5.5rem!important;padding-bottom:2rem;max-width:1500px;}
    h1,h2,h3 {color:var(--ink);letter-spacing:-.03em;}
    h1 {font-size:2.1rem!important;} h2 {font-size:1.6rem!important;} h3 {font-size:1.2rem!important;}
    [data-testid="stSidebar"] {background:#fff;border-right:1px solid #e1e8ee;}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.7rem;}
    .brand {display:flex;gap:12px;align-items:center;margin:0 0 18px;padding:4px 0 16px;border-bottom:1px solid #edf0f3;}
    .brand-icon {display:grid;place-items:center;width:44px;height:44px;flex:none;color:#b5f3e6;
      background:linear-gradient(135deg,#183451,#16756b);border-radius:14px;}
    .brand strong {font-size:21px;color:#14354d;} .brand small{display:block;color:#718499;font-size:12px;margin-top:3px;}
    .st-key-main_navigation label {border-radius:9px;padding:9px 12px;margin:2px 0;border-left:3px solid transparent;transition:background .15s,border-color .15s;}
    .st-key-main_navigation label:hover {background:#f1f8f9;}
    .st-key-main_navigation label:has(input:checked) {background:#e4f4ef;border-left-color:#168579;color:#145951;}
    button {transition:transform .12s,box-shadow .12s!important;}
    button:hover {box-shadow:0 3px 10px #16354d14;transform:translateY(-1px);}
    button:focus-visible {outline:3px solid #26a7b7!important;outline-offset:2px;}
    button[kind^="primary"] {background:#14655c;border-color:#14655c;color:white;}
    button[kind^="primary"]:hover {background:#104c47;border-color:#104c47;color:white;}
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlockBorderWrapper"]>div {background:white;border-radius:14px;}
    [data-testid="stMetric"] {background:white;padding:12px 15px;border:1px solid #e1e9ef;border-radius:12px;}
    [data-testid="stAlert"] {border-radius:12px;}
    .st-key-report_triage_card,.st-key-report_history_card,.st-key-report_reasoning_card,.st-key-report_missing_card,
    .st-key-report_triage_card>[data-testid="stVerticalBlock"],.st-key-report_history_card>[data-testid="stVerticalBlock"],
    .st-key-report_reasoning_card>[data-testid="stVerticalBlock"],.st-key-report_missing_card>[data-testid="stVerticalBlock"] {
      background:#fff!important;border:1px solid #dde6ed!important;border-radius:14px!important;
      box-shadow:0 3px 12px #18334c06;border-top:3px solid #8dc9d5!important;}
    .prototype-note {font-size:12px;color:#6d7786;border-left:3px solid #efb560;padding:7px 12px;margin-bottom:16px;background:#fffaf0;}
    .account-hero {position:relative;isolation:isolate;overflow:hidden;display:flex;align-items:center;
      justify-content:space-between;gap:24px;flex-wrap:wrap;padding:clamp(22px,4vw,42px);
      margin-bottom:10px;border-radius:22px;background:linear-gradient(118deg,#142a45,#164755 72%,#166562);color:#fff;}
    .account-hero::after {content:"";position:absolute;z-index:-1;right:-85px;top:-120px;width:330px;
      height:330px;border:1px solid #9ce8dc44;border-radius:50%;box-shadow:0 0 0 30px #9ce8dc18,0 0 0 64px #9ce8dc12;}
    .account-eyebrow {display:block;color:#526780;font-size:.72rem;font-weight:750;letter-spacing:.13em;text-transform:uppercase;}
    .account-hero .account-eyebrow {color:#b8f0e5;}
    .account-hero h1 {color:#fff;font-size:clamp(1.8rem,4vw,2.85rem)!important;padding:0;margin:5px 0;}
    .account-hero p {color:#dcf2f2;margin:0;}
    .page-hero {min-height:148px;}
    .page-hero.emergency {background:linear-gradient(115deg,#492338,#842e40);}
    .page-hero.emergency .account-eyebrow,.page-hero.emergency p {color:#ffe2e8;}
    .hero-symbol {display:grid;place-items:center;color:#b4f0e1;background:#ffffff13;
      border:1px solid #ffffff4d;border-radius:22px;width:84px;height:84px;flex:none;}
    .page-hero.emergency .hero-symbol {color:#ffe2e8;}
    .st-key-auth_workspace .page-hero {min-height:225px;}
    .st-key-auth_access [role="radiogroup"],.st-key-login_role [role="radiogroup"],
    .st-key-account_switch [role="radiogroup"],.st-key-registration_type [role="radiogroup"],
    .st-key-patient_view [role="radiogroup"] {gap:7px;flex-wrap:wrap;}
    :is(.st-key-auth_access,.st-key-login_role,.st-key-registration_type,.st-key-patient_view) [role="radiogroup"] label {
      padding:7px 11px;border:1px solid #dce6eb;border-radius:10px;background:#fff;}
    :is(.st-key-auth_access,.st-key-login_role,.st-key-registration_type,.st-key-patient_view) label:has(input:checked) {
      background:#e6f5f2;border-color:#73b9ac;color:#164b47;}
    .session-card {border:1px solid #d9eae8;background:#eff8f6;border-radius:12px;padding:12px;overflow-wrap:anywhere;}
    .session-card strong {display:block;color:#163c4c;}
    .session-card small {color:#486476;}
    .st-key-dashboard_stats [data-testid="stMetric"] {height:100%;border-top:3px solid var(--stat,#168579);}
    .st-key-dashboard_stats [data-testid="stColumn"]:nth-child(2) {--stat:#bd3c52;}
    .st-key-dashboard_stats [data-testid="stColumn"]:nth-child(3) {--stat:#a86819;}
    .st-key-dashboard_stats [data-testid="stColumn"]:nth-child(4) {--stat:#4280aa;}
    .st-key-dashboard_stats [data-testid="stColumn"]:nth-child(5) {--stat:#977126;}
    .st-key-dashboard_stats [data-testid="stColumn"]:last-child {--stat:#298468;}
    .st-key-dashboard_stats [data-testid="stMetricLabel"] p {white-space:normal;}
    .st-key-dashboard_stats [data-testid="stHorizontalBlock"] {
      display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));}
    .st-key-dashboard_stats [data-testid="stColumn"] {width:auto!important;min-width:0;}
    .queue-pill {display:inline-block;border-radius:18px;padding:4px 10px;font-weight:650;font-size:.82rem;}
    .st-key-reference_answer {border-left:4px solid #3c9b8d!important;}
    .account-counts {display:flex;gap:10px;flex-wrap:wrap;}
    .account-counts div {padding:10px 16px;border:1px solid #b7f0e34f;background:#102d4273;border-radius:14px;}
    .account-counts strong {display:block;color:#fff;font-size:1.65rem;line-height:1.2;}
    .account-counts span {color:#e0f8f5;font-size:.8rem;}
    .st-key-account_switch [role="radiogroup"] {gap:6px;flex-wrap:wrap;}
    .st-key-account_switch label,.st-key-account_queue [role="radiogroup"] label {
      border:1px solid #dce6eb;background:#fff;border-radius:10px;padding:8px 12px;margin:0;}
    .st-key-account_switch label:hover,.st-key-account_queue [role="radiogroup"] label:hover {background:#f1faf8;}
    .st-key-account_switch label:has(input:checked),.st-key-account_queue label:has(input:checked) {
      background:#e6f5f2;border-color:#73b9ac;color:#164b47;}
    .st-key-account_queue [role="radiogroup"] {gap:7px;}
    .st-key-account_queue label,.account-identity {overflow-wrap:anywhere;}
    .account-identity {display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:16px;
      border-radius:13px;background:#edf6f7;border:1px solid #d6e9ec;}
    .account-identity > div {min-width:0;}
    .account-avatar {display:grid;place-items:center;flex:0 0 42px;height:42px;border-radius:13px;
      background:#c9e9e6;color:#174f4e;font-weight:750;font-size:1.15rem;}
    .account-identity strong,.account-identity small {display:block;}
    .account-identity strong {color:#15364a;font-size:1.25rem;}
    .account-identity small {color:#486079;}
    .account-status {font-size:.75rem;font-weight:700;border-radius:24px;padding:4px 10px;margin-left:auto;}
    .account-status-pending {background:#fff0cd;color:#734909;}
    .account-status-enabled {background:#d7eee5;color:#225c4c;}
    .account-status-disabled {background:#e6ebf2;color:#475872;}
    :is(.st-key-account_queue,.st-key-account_detail,.st-key-account_empty,.st-key-auth_panel,.st-key-reference_answer,
        [class*="st-key-queue_row_"]) {background:#fff;border-radius:14px;}
    @media(max-width:800px) {
      :is(.st-key-account_workspace,.st-key-auth_workspace) [data-testid="stHorizontalBlock"] {flex-direction:column;}
      :is(.st-key-account_workspace,.st-key-auth_workspace) [data-testid="stColumn"] {width:100%!important;flex:auto!important;}
    }
    .patient-banner {display:grid;grid-template-columns:1.5fr 1fr .8fr;gap:22px;background:linear-gradient(110deg,#e0f2f5,#edf7fb);border:1px solid #c9e4eb;border-radius:16px;padding:23px;margin:8px 0 16px;}
    .identity {display:flex;gap:15px;align-items:center;}.avatar {width:62px;height:62px;flex-shrink:0;border-radius:50%;background:#c4e4ee;color:#12627a;display:flex;align-items:center;justify-content:center;font-size:27px;font-weight:700;}
    .patient-banner strong {font-size:20px;color:#163b53;}.patient-banner small {display:block;color:#526f81;margin-top:6px;font-size:13px;}
    .banner-cell {border-left:1px solid #bad8e1;padding-left:24px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:8px;}
    .banner-label {font-size:12px;color:#486879;font-weight:600;text-transform:uppercase;letter-spacing:.07em;}
    .badge {border:1px solid;border-radius:30px;padding:8px 19px;font-size:18px;font-weight:700;}
    .badge-critical {color:#a32235;background:#ffe0e5;border-color:#e9a5af;}
    .badge-urgent {color:#865400;background:#fff0c8;border-color:#e8c679;}
    .badge-routine {color:#215d8d;background:#ddebfc;border-color:#adcde9;}
    .badge-unknown {color:#654d1b;background:#f9efda;border-color:#dfcca4;}
    .badge-waiting {color:#12677c;background:#c9eaf3;border-color:#98d0df;}
    .badge-care {color:#936018;background:#fff0d6;border-color:#e9c98e;}
    .badge-completed {color:#1b6a53;background:#d6eee6;border-color:#abd5c7;}
    @media(max-width:800px){.patient-banner{grid-template-columns:1fr;gap:14px}.banner-cell{border-left:0;border-top:1px solid #bad8e1;padding:14px 0 0}}
    @media(max-width:600px){.hero-symbol{display:none}.page-hero{min-height:0}}
    @media(prefers-reduced-motion:reduce){button{transition:none!important}button:hover{transform:none}}
    </style>''', unsafe_allow_html=True)


def sidebar_brand():
    st.markdown(f'<div class="brand"><div class="brand-icon">{_symbol("pulse", 24)}</div>'
                '<div><strong>MediAgent AI</strong><small>Local healthcare support</small></div></div>',
                unsafe_allow_html=True)


def _symbol(icon, size):
    paths = {
        'pulse': 'M2 12h5l3-7 4 14 3-7h5',
        'visit': 'M12 5v14M5 12h14',
        'report': 'M6 3h9l4 4v14H6zM10 11h5m-5 4h5',
        'time': 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z',
        'search': 'M17 17l4 4M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0z',
        'access': 'M6 10h12v11H6zM8 10V7a4 4 0 0 1 8 0v3m-4 4v3',
        'alert': 'M12 3l10 18H2zM12 9v4m0 3v1',
    }
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" fill="none" '
            f'stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="{paths[icon]}"/></svg>')


def page_hero(section, title, description, icon, *, emergency=False):
    variant = ' emergency' if emergency else ''
    st.markdown(f'''
        <div class="account-hero page-hero{variant}">
            <div><span class="account-eyebrow">{html.escape(section)}</span>
                <h1>{html.escape(title)}</h1><p>{html.escape(description)}</p>
            </div>
            <div class="hero-symbol">{_symbol(icon, 45)}</div>
        </div>
        ''', unsafe_allow_html=True)


def session_card(user):
    st.markdown(f'<div class="session-card"><span class="account-eyebrow">Signed in</span>'
                f'<strong>{html.escape(user["display_name"])}</strong>'
                f'<small>{html.escape(user["role"])}</small></div>', unsafe_allow_html=True)


def patient_banner(record, review=None):
    esc = lambda value:html.escape(str(value), quote=True)
    ai = record.get('classification') or {}
    priority = (review or ai).get('priority', 'Awaiting assessment')
    severity = {'Critical':'critical','Urgent':'urgent','Non-urgent':'routine'}.get(priority, 'unknown')
    status = record.get('care_status', 'Not saved')
    status_class = {'Waiting':'waiting','In care':'care','Completed':'completed'}.get(status,'unknown')
    name = record.get('patient_name') or 'Unnamed patient'
    source = 'Staff-assessed priority' if review else 'AI-suggested priority'
    return f'''<div class="patient-banner">
    <div class="identity"><div class="avatar">{esc(name[0].upper())}</div><div><strong>{esc(name)}</strong>
    <small>Patient ID {esc(record.get('patient_id','Not saved'))} · {esc(record['age'])} years · {esc(record['gender'])}</small>
    <small>{esc(record.get('visit_type','Unsaved report'))}</small></div></div>
    <div class="banner-cell"><div class="banner-label">{esc(source)}</div><span class="badge badge-{severity}">{esc(priority)}</span></div>
    <div class="banner-cell"><div class="banner-label">Care status</div><span class="badge badge-{status_class}">{esc(status)}</span></div></div>'''


def report_cards(record, review=None):
    intake = record.get('intake') or {}
    ai = record.get('classification') or {}
    left,right = st.columns(2, gap='medium')
    with left:
        with st.container(border=True, key='report_triage_card'):
            st.subheader('🩺 Triage details')
            st.write('**Reported symptoms**')
            st.write(record['symptoms'])
            for label,key in [('Onset / duration','Onset / duration'),('Progression / triggers','Progression / triggers'),('Pain score','Pain score (0-10)'),('Breathing','Breathing')]:
                st.write('**'+label+':** '+str(intake.get(key) or 'Not recorded'))
        with st.container(border=True, key='report_reasoning_card'):
            st.subheader('💡 AI reasoning')
            st.write(ai.get('reasoning') or 'No AI explanation is available for this visit.')
            st.caption('Model-generated explanation for review; not a diagnosis.')
    with right:
        with st.container(border=True, key='report_history_card'):
            st.subheader('📋 Medical history context')
            for key in ('Medical conditions','Current medicines','Allergies','Past procedures / admissions','Pregnancy context'):
                st.write('**'+key+':** '+str(intake.get(key) or 'Not recorded'))
        with st.container(border=True, key='report_missing_card'):
            st.subheader('❔ Missing information')
            st.write(ai.get('uncertainty') or 'No AI assessment is available. A qualified staff member must assess missing information.')
            if review:
                st.write('**Recorded staff decision:** '+review['priority'])
                st.write(review['reason'])
