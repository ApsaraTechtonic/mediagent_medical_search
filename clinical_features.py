"""Intake, readable saved reports and source-linked emergency information."""
import streamlit as st
from ui_theme import page_hero

EMERGENCY_SOURCES = {
    'India emergency services': 'https://112.gov.in/faq',
    'First-aid guidance': 'https://www.resus.org.uk/professional-library/2025-resuscitation-guidelines/first-aid-guidelines',
}


def intake_questions():
    st.caption('Record what is known. Leave unknown details blank; do not guess measurements. '
               'This intake checklist is not a validated triage score.')
    current, history, vitals = st.tabs(['Current symptoms', 'Medical history', 'Recorded vitals'])
    result = {}
    with current:
        a,b = st.columns(2)
        result['Onset / duration'] = a.text_input('When did symptoms start? How long have they lasted?', max_chars=250)
        result['Progression / triggers'] = b.text_input('Getting better or worse? Any triggers?', max_chars=250)
        result['Pain score (0-10)'] = a.selectbox('Pain score, if reported', ['Not recorded']+[str(i) for i in range(11)])
        result['Breathing'] = b.selectbox('Reported breathing status', ['Not recorded', 'No difficulty reported', 'Difficulty breathing reported'])
        result['Responsiveness'] = a.selectbox('Observed responsiveness', ['Not recorded', 'Alert', 'Responds to voice', 'Responds to pain', 'Unresponsive'])
        result['Associated symptoms'] = b.text_input('Other associated symptoms', max_chars=500)
    with history:
        a,b = st.columns(2)
        result['Allergies'] = a.text_input('Known allergies and reactions', max_chars=500)
        result['Current medicines'] = b.text_input('Current medicines / recent doses, if known', max_chars=500)
        result['Medical conditions'] = a.text_input('Relevant medical conditions', max_chars=500)
        result['Past procedures / admissions'] = b.text_input('Previous procedures or hospital admissions', max_chars=500)
        result['Pregnancy context'] = a.selectbox('Pregnancy context, if relevant and known',
            ['Not recorded', 'Not applicable', 'Pregnant', 'Possible pregnancy', 'Not pregnant'])
        result['Recent injury / exposure'] = b.text_input('Recent injury, illness contact or exposure', max_chars=500)
    with vitals:
        st.caption('Enter actual recorded readings with units; these are not measured by the app.')
        a,b,c = st.columns(3)
        for column,label,placeholder in [(a,'Blood pressure','e.g. 120/80 mmHg'),(b,'Heart rate','e.g. 80 bpm'),
            (c,'Respiratory rate','e.g. 16 breaths/min'),(a,'Oxygen saturation','e.g. 98%'),
            (b,'Temperature','e.g. 37 C'),(c,'Blood glucose','Include mg/dL or mmol/L')]:
            result[label] = column.text_input(label, placeholder=placeholder, max_chars=100)
    return {k:v.strip() for k,v in result.items() if v.strip() and v!='Not recorded'}


def report_markdown(record, review=None):
    lines = ['# MediAgent - saved visit report',
        f"Patient ID: {record.get('patient_id', 'Unsaved')}",
        f"Name: {record.get('patient_name') or 'Not recorded'}",
        f"Visit date: {record.get('created_at', 'Not saved')}",
        f"Visit type: {record.get('visit_type', 'Not recorded')}",
        f"Care status: {record.get('care_status', 'Not recorded')}",
        f"Age: {record['age']} | Gender: {record['gender']}",
        '\n## Reported symptoms', record['symptoms'], '\n## Recorded intake and medical history']
    lines += [f'{k}: {v}' for k,v in record.get('intake', {}).items()] or ['No additional intake recorded for this visit.']
    lines += ['\n## Staff clinical decision']
    if review:
        lines += ['Priority: '+review['priority'], 'Reason: '+review['reason'],
                  'Recorded: '+review.get('created_at', 'Not recorded')]
    else:
        lines += ['Not yet recorded.']
    lines += ['\n## Original AI suggestion']
    ai = record.get('classification')
    if ai:
        lines += ['Priority: '+ai['priority'], 'Possible immediate emergency flag: '+str(ai['immediate_emergency']),
                  'Reasoning: '+ai['reasoning'], '\n### Current concerns']
        lines += ['- '+x for x in ai['concerns']] or ['None listed; this does not establish safety.']
        lines += ['\n### Historical context']
        lines += ['- '+x for x in ai['historical_context']] or ['None listed.']
        lines += ['\n### Uncertainty / missing information', ai['uncertainty']]
    else:
        lines += ['Unavailable. Continue qualified human assessment.']
    lines += ['\n---', 'Hackathon prototype. AI output is unvalidated and requires clinician review. '
              'Recorded history belongs to this visit; earlier visits do not establish current findings.']
    return '\n\n'.join(lines)


def emergency_information():
    page_hero('Emergency guide', 'Emergency help and guidance',
              'Find emergency contacts and steps to follow while help is on the way.', 'alert', emergency=True)
    st.error('For a possible emergency, call for help now. Do not wait for AI or complete this form first.')
    country = st.selectbox('Your location', ['India', 'Outside India / other location'])
    if country == 'India':
        st.metric('India: police, fire and medical emergencies', '112')
        st.markdown('[Call 112](tel:112) · [Official emergency information](https://112.gov.in/faq)')
        st.caption('112 is the nationwide integrated emergency number. A desktop browser may not support calling.')
    else:
        st.info('Use the emergency number for your actual location. The India number shown in this app is not a worldwide contact directory.')
    st.write('**While contacting emergency services**')
    st.write('Check that it is safe to approach. Give the dispatcher your exact location, '
             'what happened, and whether the person responds and is breathing normally. '
             'Use speakerphone if possible and follow dispatcher instructions.')
    st.write('**Unresponsive or not breathing normally:** call emergency services immediately '
             'and follow their CPR/AED instructions. Get a trained helper and an AED if available.')
    st.write('**Severe bleeding:** call for help and apply firm direct pressure to the bleeding site '
             'with a clean dressing if it is safe to do so. Follow dispatcher instructions.')
    st.caption('General first-aid information, not a diagnosis or personalised treatment plan. '
               'In a healthcare facility, activate your local emergency response procedure.')
    for label,url in EMERGENCY_SOURCES.items():
        st.markdown(f'[{label}]({url})')
    st.caption('Sources checked 1 November 2026. No AI request is needed to open this page.')
