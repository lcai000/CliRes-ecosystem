import google.generativeai as genai
import toml
from pathlib import Path

def list_available_models():
    """
    Connects to Google Gemini API and lists all models available to your API key.
    Useful for debugging '404 model not found' errors.
    """
    print("--- Checking Available Gemini Models ---")
    
    # 1. robustly find the project root and secrets file using pathlib
    # This file is in helpers/, so parent is project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    secrets_path = project_root / '.streamlit' / 'secrets.toml'
    
    api_key = None
    
    if secrets_path.exists():
        try:
            secrets = toml.load(secrets_path)
            api_key = secrets.get("google_api_key")
            print(f"✅ Found API Key in {secrets_path}")
        except Exception as e:
            print(f"❌ Error reading secrets.toml: {e}")
    else:
        print(f"❌ Secrets file not found at: {secrets_path}")
        print("Please ensure you have created .streamlit/secrets.toml with google_api_key defined.")
        return

    if not api_key:
        print("❌ 'google_api_key' not found in secrets file.")
        return

    # 2. Configure and List
    try:
        genai.configure(api_key=api_key)
        
        print("\nQuerying Google API for models...")
        print("(This may take a moment)\n")
        
        models = genai.list_models()
        
        found_any = False
        print(f"{'Model Name':<30} | {'Supported Methods'}")
        print("-" * 60)
        
        for m in models:
            found_any = True
            # We specifically care about 'generateContent' for the chatbot
            methods = ", ".join(m.supported_generation_methods)
            print(f"{m.name:<30} | {methods}")
            
        if not found_any:
            print("\n⚠️ No models returned. Check if your API key has correct permissions.")
            
    except Exception as e:
        print(f"\n❌ API Error: {e}")

if __name__ == "__main__":
    list_available_models()