"""Opt-in browser speech input; no audio is received or stored by Python."""
from pathlib import Path
import streamlit as st
from streamlit.components.v1 import declare_component

_voice = declare_component('mediagent_voice_input', path=str(Path(__file__).parent/'voice_component'))


def voice_input():
    with st.expander('Use voice to enter a reference question'):
        st.caption('Browser dictation may send audio to your browser provider and may require internet. '
                   'This is separate from local Ollama inference. Use general questions without patient identifiers. '
                   'Availability depends on your browser and microphone permissions.')
        enabled = st.checkbox('Enable browser voice input', key='voice_enabled')
        if enabled:
            value = _voice(key='knowledge_voice', default=None)
            if isinstance(value, dict) and value.get('id') != st.session_state.get('voice_applied'):
                transcript = value.get('text')
                if isinstance(transcript, str) and transcript.strip():
                    st.session_state['knowledge_question'] = transcript[:6000]
                    st.session_state['voice_applied'] = value.get('id')
            st.caption('Click Use this transcript, then review the normal question box and click Search Medical Database. '
                       'Dictation does not submit a search automatically.')
