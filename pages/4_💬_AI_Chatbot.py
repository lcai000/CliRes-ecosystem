import streamlit as st
import pandas as pd
from openrouter import OpenRouter  # Using the official OpenRouter SDK
import os
import re
from typing import List, Any

# --- 1. Check for Data and API Key ---
st.header("💬 Arbor - AI Data Assistant")
st.info("Powered by OpenRouter (Llama 3.2 3B Free) - Secure Web Version--STILL IN DEVELOPMENT!")

if 'combined_df' not in st.session_state or st.session_state['combined_df'].empty:
    st.info("👋 Hi! Please load some data on the Home page first so I have something to talk about.")
    st.stop()

df = st.session_state['combined_df']

api_key = st.secrets.get("openrouter_api_key")
if not api_key:
    st.error("OpenRouter API Key not found. Please add `openrouter_api_key` to your `.streamlit/secrets.toml` file.")
    st.stop()

# --- 2. Initialize Chat History ---
if "messages" not in st.session_state:
    st.session_state.messages = []  # type: ignore

# Display chat history 
for message in st.session_state.messages:
    if message["role"] != "system":  # Hide the system prompt from the UI
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# --- 3. Educational Context & System Prompt ---
plants = df['Plant Name'].unique().tolist()
columns = df.columns.tolist()

if 'Sample Time (UTC)' in df.columns:
    min_date = df['Sample Time (UTC)'].min()
    max_date = df['Sample Time (UTC)'].max()
    if pd.api.types.is_datetime64_any_dtype(df['Sample Time (UTC)']):
        min_date = min_date.strftime('%Y-%m-%d')
        max_date = max_date.strftime('%Y-%m-%d')
else:
    min_date = "Unknown"
    max_date = "Unknown"

# FIX 1: Use markdown to drastically reduce payload size and prevent timeouts!
stats = df.describe().round(2).to_markdown()

system_prompt = f"""
You are Arbor, an expert Environmental Data Scientist and Dendrologist for the Cli-Res Project.

**Your Knowledge Base:**
1.  **Project Context:**
    - The Cli-Res Project focuses on monitoring tree health in urban environments.
    - Data includes temperature, humidity, rainfall, and dendrometer readings.
2.  **Dataset Info:**
    - **Date Range:** {min_date} to {max_date}
    - **Plants/Sensors:** {", ".join(map(str, plants))}
    - **Columns:** {", ".join(map(str, columns))}
3.  **Statistical Summary of Data:**
    {stats}

**Capabilities & Restrictions:**
- **Q&A:** Answer questions based on the summary.
- **Graphing (RESTRICTED):** You do NOT have the ability to execute code or display graphs directly on the screen. 
- If the user asks for a graph, you must write the Python code for them to copy/paste locally. Wrap it in ```python ... ```.

**Instructions:**
- Be professional, highly technical, and concise. 
- Never attempt to run code. Only provide the text.
"""

# --- 4. User Input Area ---
if raw_prompt := st.chat_input("Ask about your data..."):
    prompt = re.sub(r'<[^>]*>', '', raw_prompt).strip()
    
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Start the list with the system prompt outside the loop so it doesn't duplicate
    api_messages: List[Any] = [{"role": "system", "content": system_prompt}]

    # Build the message history for the API
    for msg in st.session_state.messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    # --- 5. Generate Response ---
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            # Using the official OpenRouter context manager right here
            with OpenRouter(api_key=api_key) as client:  # type: ignore
                
                # Show a temporary spinner while the model thinks
                with st.spinner("Arbor is analyzing your forestry data..."):
                    response = client.chat.send(
                        # FIX 2: Swap to the ultra-fast 3B model to avoid provider timeouts
                        model="meta-llama/llama-3.2-3b-instruct:free",  
                        messages=api_messages
                    )
                
                # Extract response exactly like your example snippet
                full_response = response.choices[0].message.content
                
                # Render it to the screen
                message_placeholder.markdown(full_response)

            # Save assistant response to history
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            st.error(f"OpenRouter API Error: {e}")