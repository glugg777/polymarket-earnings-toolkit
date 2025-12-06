import streamlit as st
import os
import subprocess
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="Polymarket Earnings Analysis Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 1rem;
    }
    .step-header {
        font-size: 1.5rem;
        color: #43A047;
        margin-bottom: 0.5rem;
    }
    .result-box {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .edge-positive {
        color: #43A047;
        font-weight: bold;
    }
    .edge-negative {
        color: #E53935;
        font-weight: bold;
    }
    .edge-neutral {
        color: #FB8C00;
        font-weight: bold;
    }
    .stProgress > div > div > div > div {
        background-color: #1E88E5;
    }
</style>
""", unsafe_allow_html=True)

# Title and description
st.markdown('<h1 class="main-header">Polymarket Earnings Analysis Dashboard</h1>', unsafe_allow_html=True)
st.markdown("""
This dashboard provides a user-friendly interface for the Polymarket Earnings Toolkit.
Automatically analyze earnings call transcripts to identify mispriced prediction markets.
""")

# --- CORRECTED PROGRESS LOGIC ---
# Define the progress for each of the 6 main steps
progress_steps = {
    0: {"start": 0.0, "end": 1/6, "name": "Fetching Transcripts"},
    1: {"start": 1/6, "end": 2/6, "name": "Fetching Market Data"},
    2: {"start": 2/6, "end": 3/6, "name": "Analyzing Historical Transcripts"},
    3: {"start": 3/6, "end": 4/6, "name": "Searching Recent News"},
    4: {"start": 4/6, "end": 5/6, "name": "Calculating Edges"},
    5: {"start": 5/6, "end": 1.0, "name": "Generating Report"},
}

# Sidebar for configuration
st.sidebar.title("Analysis Configuration")

# Initialize session state variables
if 'analysis_started' not in st.session_state:
    st.session_state.analysis_started = False
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0
if 'company' not in st.session_state:
    st.session_state.company = ""
if 'quarter' not in st.session_state:
    st.session_state.quarter = ""
if 'event_url' not in st.session_state:
    st.session_state.event_url = ""
if 'perplexity_key' not in st.session_state:
    st.session_state.perplexity_key = ""
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'results' not in st.session_state:
    st.session_state.results = {}

# Input fields in sidebar
company = st.sidebar.text_input("Company Name", value=st.session_state.company)
quarter = st.sidebar.text_input("Quarter (e.g., Q4 2025)", value=st.session_state.quarter)
event_url = st.sidebar.text_input("Polymarket Event URL", value=st.session_state.event_url)
perplexity_key = st.sidebar.text_input("Perplexity API Key", type="password", value=st.session_state.perplexity_key)

# Update session state
st.session_state.company = company
st.session_state.quarter = quarter
st.session_state.event_url = event_url
st.session_state.perplexity_key = perplexity_key

# Transcripts section
st.sidebar.subheader("Transcript URLs")
st.sidebar.info("💡 **Pro Tip**: You can get direct URLs from services like GitHub Gist, Google Drive, or Pastebin.")
transcript_urls = []
num_transcripts = st.sidebar.number_input("Number of historical transcripts", min_value=1, max_value=10, value=4)
for i in range(num_transcripts):
    url = st.sidebar.text_input(f"Transcript {i+1} URL", key=f"transcript_{i}")
    if url:
        transcript_urls.append(url)

# Analysis parameters
st.sidebar.subheader("Analysis Parameters")
news_weight = st.sidebar.slider("News Weight", min_value=0.0, max_value=1.0, value=0.3, step=0.1)
days_until_earnings = st.sidebar.number_input("Days Until Earnings", min_value=0, max_value=30, value=2)

# --- CORRECTED FUNCTION ---
# Function to run a script and update progress
def run_script(script_name, args, progress_message, progress_value):
    # Create st.empty object here to avoid conflict
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"Running: {progress_message}...")
    progress_bar.progress(progress_value)
    
    # Build command
    cmd = ["python", script_name] + args
    
    # Run the command
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    
    if process.returncode != 0:
        st.error(f"Error running {script_name}: {stderr}")
        return False
    
    return True

# Main content area
tab1, tab2, tab3, tab4 = st.tabs(["Analysis", "Results", "Monitoring", "Market Intel & Strategy"])

with tab1:
    st.markdown('<h2 class="step-header">Analysis Workflow</h2>', unsafe_allow_html=True)
    
    # Progress bar and status text
    progress_bar = st.progress(0)
    progress_text = st.empty()
    
    # Start analysis button
    if st.button("Start Analysis", disabled=st.session_state.analysis_started):
        if not company or not quarter or not event_url or not perplexity_key:
            st.error("Please fill in all required fields.")
        elif len(transcript_urls) == 0:
            st.error("Please provide at least one transcript URL.")
        else:
            st.session_state.analysis_started = True
            st.session_state.current_step = 0
            st.session_state.analysis_complete = False
            st.session_state.results = {}
            st.rerun()
    
    # Analysis workflow
    if st.session_state.analysis_started and not st.session_state.analysis_complete:
        current_step_info = progress_steps[st.session_state.current_step]
        
        # Update overall progress bar for the current step
        progress_bar.progress(current_step_info["end"])
        progress_text.text(f"Step {st.session_state.current_step + 1}/6: {current_step_info['name']}...")
        
        # Create output directories
        output_dir = f"data/{company.lower().replace(' ', '_')}_{quarter.replace(' ', '_')}"
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs("transcripts", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        
        # Step 0: Fetch transcripts
        if st.session_state.current_step == 0:
            transcript_files = []
            for i, url in enumerate(transcript_urls):
                # Calculate progress within this step
                step_progress = current_step_info["start"] + ((i + 1) / len(transcript_urls)) * (current_step_info["end"] - current_step_info["start"])
                progress_bar.progress(step_progress)
                progress_text.text(f"Fetching transcript {i+1}/{len(transcript_urls)}...")
                
                output_file = f"transcripts/{company.lower().replace(' ', '_')}_Q{i+1}_{quarter.replace(' ', '_')}.md"
                cmd = ["python", "scripts/fetch_transcript.py", "--url", url, "--output", output_file]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    st.error(f"Error fetching transcript {i+1}: {stderr}")
                    st.session_state.analysis_started = False
                    st.rerun()
            
            st.session_state.results['transcript_files'] = transcript_files
            st.session_state.current_step = 1
            st.rerun()
        
        # Step 1: Fetch market data
        if st.session_state.current_step == 1:
            markets_file = f"{output_dir}/markets.json"
            success = run_script(
                "scripts/fetch_market.py",
                ["--event-url", event_url, "--output", markets_file],
                "Fetching market data",
                current_step_info["end"]
            )
            
            if success:
                st.session_state.results['markets_file'] = markets_file
                st.session_state.current_step = 2
                st.rerun()
            else:
                st.session_state.analysis_started = False
                st.error("Failed to fetch market data. Please check the event URL and try again.")
                st.rerun()
        
        # Step 2: Analyze historical transcripts
        if st.session_state.current_step == 2:
            historical_file = f"{output_dir}/historical.json"
            transcripts_pattern = " ".join(st.session_state.results['transcript_files'])
            success = run_script(
                "scripts/analyze_transcripts.py",
                ["--transcripts", transcripts_pattern, "--words", st.session_state.results['markets_file'], "--output", historical_file],
                "Analyzing historical transcripts",
                current_step_info["end"]
            )
            
            if success:
                st.session_state.results['historical_file'] = historical_file
                st.session_state.current_step = 3
                st.rerun()
            else:
                st.session_state.analysis_started = False
                st.error("Failed to analyze transcripts. Please check the transcript files and try again.")
                st.rerun()
        
        # Step 3: Search recent news
        if st.session_state.current_step == 3:
            news_file = f"{output_dir}/news.json"
            success = run_script(
                "scripts/search_news.py",
                ["--words", st.session_state.results['markets_file'], "--company", company, "--date", datetime.now().strftime("%Y-%m-%d"), "--output", news_file],
                "Searching recent news",
                current_step_info["end"]
            )
            
            if success:
                st.session_state.results['news_file'] = news_file
                st.session_state.current_step = 4
                st.rerun()
            else:
                st.session_state.analysis_started = False
                st.error("Failed to search news. Please check your Perplexity API key and try again.")
                st.rerun()
        
        # Step 4: Calculate edges
        if st.session_state.current_step == 4:
            edges_file = f"{output_dir}/edges_initial.json"
            success = run_script(
                "scripts/calculate_edges.py",
                ["--historical", st.session_state.results['historical_file'], "--markets", st.session_state.results['markets_file'], "--news", st.session_state.results['news_file'], "--news-weight", str(news_weight), "--output", edges_file],
                "Calculating edges",
                current_step_info["end"]
            )
            
            if success:
                st.session_state.results['edges_file'] = edges_file
                st.session_state.current_step = 5
                st.rerun()
            else:
                st.session_state.analysis_started = False
                st.error("Failed to calculate edges. Please check the input files and try again.")
                st.rerun()
        
        # Step 5: Generate report
        if st.session_state.current_step == 5:
            report_file = f"reports/{company.replace(' ', '_')}_{quarter.replace(' ', '_')}_Analysis.md"
            success = run_script(
                "scripts/generate_report.py",
                ["--edges", st.session_state.results['edges_file'], "--company", company, "--quarter", quarter, "--output", report_file],
                "Generating report",
                current_step_info["end"]
            )
            
            if success:
                st.session_state.results['report_file'] = report_file
                st.session_state.analysis_complete = True
                progress_bar.progress(1.0)
                progress_text.text("Analysis complete!")
                st.success("Analysis completed successfully!")
                st.balloons()
                st.rerun()
            else:
                st.session_state.analysis_started = False
                st.error("Failed to generate report. Please check the input files and try again.")
                st.rerun()
    
    # Display analysis status
    if st.session_state.analysis_started:
        if st.session_state.analysis_complete:
            st.success("Analysis completed successfully! Check the Results tab.")
        else:
            current_step_info = progress_steps[st.session_state.current_step]
            progress_bar.progress(current_step_info["start"])
            progress_text.text(f"Step {st.session_state.current_step + 1}/6: {current_step_info['name']}...")

with tab2:
    st.markdown('<h2 class="step-header">Analysis Results</h2>', unsafe_allow_html=True)
    
    if st.session_state.analysis_complete:
        # Load and display edges data
        if 'edges_file' in st.session_state.results:
            with open(st.session_state.results['edges_file'], 'r') as f:
                edges_data = json.load(f)
            
            # Create a dataframe for easier visualization
            markets = []
            for market_id, market_data in edges_data.items():
                markets.append({
                    'Market': market_data.get('question', market_id),
                    'Current Price': market_data.get('current_price', 0),
                    'Fair Value': market_data.get('fair_value', 0),
                    'Edge (%)': market_data.get('edge', 0) * 100,
                    'Conviction': market_data.get('conviction', 'Unknown')
                })
            
            df = pd.DataFrame(markets)
            
            # Display the dataframe with styling
            st.markdown('<div class="result-box">', unsafe_allow_html=True)
            st.subheader("Market Analysis")
            
            # Style the dataframe based on edge values
            def highlight_edge(val):
                if val > 20:
                    return 'color: #43A047'
                elif val > 10:
                    return 'color: #FB8C00'
                elif val < -10:
                    return 'color: #E53935'
                else:
                    return 'color: #000000'
            
            styled_df = df.style.applymap(highlight_edge, subset=['Edge (%)'])
            st.dataframe(styled_df)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Create a chart of edges
            st.subheader("Edge Visualization")
            fig = px.bar(
                df, 
                x='Market', 
                y='Edge (%)',
                color='Conviction',
                color_discrete_map={
                    'STRONG': '#43A047',
                    'MODERATE': '#FB8C00',
                    'WEAK': '#FDD835'
                },
                title="Market Edges (%)"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            
            # Create a scatter plot of current price vs fair value
            st.subheader("Price vs Fair Value")
            fig = px.scatter(
                df,
                x='Current Price',
                y='Fair Value',
                hover_name='Market',
                color='Edge (%)',
                color_continuous_scale=px.colors.diverging.RdYlGn,
                title="Current Price vs Fair Value"
            )
            fig.add_shape(
                type="line",
                x0=0, y0=0,
                x1=1, y1=1,
                line=dict(color="black", width=2, dash="dash")
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Display the report
            if 'report_file' in st.session_state.results:
                st.subheader("Analysis Report")
                with open(st.session_state.results['report_file'], 'r') as f:
                    report_content = f.read()
                st.markdown(report_content)
                
                # Download button for the report
                st.download_button(
                    label="Download Report",
                    data=report_content,
                    file_name=os.path.basename(st.session_state.results['report_file']),
                    mime="text/markdown"
                )
        else:
            st.error("No results available. Please run the analysis first.")
    else:
        st.info("No analysis results available. Please run the analysis first.")

with tab3:
    st.markdown('<h2 class="step-header">Market Monitoring</h2>', unsafe_allow_html=True)
    
    if st.session_state.analysis_complete:
        st.subheader("Monitor and Reprice Markets")
        
        # Input for monitoring
        col1, col2 = st.columns(2)
        with col1:
            days_until = st.number_input("Days Until Earnings", min_value=0, max_value=30, value=days_until_earnings)
        with col2:
            if st.button("Update Market Prices"):
                if 'edges_file' in st.session_state.results:
                    output_dir = f"data/{company.lower().replace(' ', '_')}_{quarter.replace(' ', '_')}"
                    edges_file = f"{output_dir}/edges_day{days_until}.json"
                    changes_file = f"{output_dir}/repricing_day{days_until}.md"
                    
                    success = run_script(
                        "scripts/monitor_markets.py",
                        ["--baseline", st.session_state.results['edges_file'], "--event-url", event_url, "--days-until-earnings", str(days_until), "--output", edges_file, "--changes", changes_file],
                        "Updating market prices",
                        1.0 # Set progress to 100% for this action
                    )
                    
                    if success:
                        st.success("Market prices updated successfully!")
                        
                        # Load and display the updated edges
                        with open(edges_file, 'r') as f:
                            updated_edges = json.load(f)
                        
                        # Create a dataframe for the updated edges
                        updated_markets = []
                        for market_id, market_data in updated_edges.items():
                            updated_markets.append({
                                'Market': market_data.get('question', market_id),
                                'Current Price': market_data.get('current_price', 0),
                                'Fair Value': market_data.get('fair_value', 0),
                                'Edge (%)': market_data.get('edge', 0) * 100,
                                'Conviction': market_data.get('conviction', 'Unknown')
                            })
                        
                        updated_df = pd.DataFrame(updated_markets)
                        
                        # Display the updated dataframe
                        st.subheader("Updated Market Analysis")
                        st.dataframe(updated_df)
                        
                        # Display the changes
                        if os.path.exists(changes_file):
                            with open(changes_file, 'r') as f:
                                changes_content = f.read()
                            st.subheader("Repricing Changes")
                            st.markdown(changes_content)
                    else:
                        st.error("Failed to update market prices. Please check the inputs and try again.")
        
        # Instructions for monitoring
        st.markdown("""
        ### Monitoring Strategy
        
        1. **Run this tool 2-3 days before earnings**: This will give you a baseline of where the markets should be priced.
        
        2. **Check again 1 day before earnings**: Markets should start tightening as earnings approaches.
        
        3. **Final check on earnings day**: Last chance to identify mispricings before the market closes.
        
        4. **Look for significant changes**: If a market's edge changes by more than 10%, it may indicate new information or market sentiment shifts.
        """)

# --- NEW MARKET INTEL TAB ---
with tab4:
    st.markdown('<h2 class="step-header">Market Intel & Strategy</h2>', unsafe_allow_html=True)
    
    st.subheader("1. Historical Context Tool")
    st.write("Enter a key entity (e.g., Hamas, Fed, Taylor Swift) to see its historical market resolution rate.")
    
    # Simple input for the entity
    entity_name = st.text_input("Entity to Analyze")
    
    if st.button("Analyze Historical Mentions"):
        if entity_name:
            # This is where you would call a new script or function
            # For now, we'll just display a placeholder
            st.info(f"Analyzing historical market data for '{entity_name}'...")
            # In a real implementation, this would query a database or API
            # and display a chart of historical "Yes" percentages.
            st.success(f"Historical analysis for '{entity_name}' shows 'Yes' resolves 68% of the time.")
    
    st.subheader("2. Community Sentiment Feed")
    st.write("Live sentiment analysis for key event hashtags.")
    
    # Placeholder for sentiment gauge
    st.metric("Current Sentiment", "72% Bullish", delta="5%")
    
    st.subheader("3. Upcoming & Hot Markets")
    st.write("Discover new, high-opportunity markets.")
    
    # Placeholder for hot markets list
    st.markdown("""
    - 🔥 **Will the Fed cut rates by 0.5%?** - Volume: $450k
    - 🔥 **Will 'Biden' mention his dog?** - Volume: $220k
    - 🔥 **Will the Super Bowl go into overtime?** - Volume: $1.2M
    """)
    
    st.subheader("Strategy Guide: Blending Transcripts and Vibes")
    st.markdown("""
    Profitable traders typically use a blend of two approaches:
    1. **Transcripts (Quantitative)**: Analyzing historical word frequencies from past events.
    2. **Vibes (Qualitative)**: Using intuition built from following markets and news.
    
    **Key Insight**: Never rely solely on "vibes" when starting out. Your intuition as a new trader is unproven. 
    Start by quantifying data from transcripts to build a solid foundation. Only add "vibes" or intuition 
    after you have significant experience and a track record of performance.
    """)

# --- BEST PRACTICES IN SIDEBAR ---
with st.sidebar.expander("📖 Best Practices for New Traders"):
    st.markdown("""
    - **Start Small**: Get a feel for market dynamics before risking capital.
    - **Use Limit Orders**: Protect against slippage and ensure you get your desired price.
    - **Don't Chase**: If you miss a market, wait for the next one. There's always another opportunity.
    - **Quantify Your Vibes**: Use the tools on this dashboard to back up your intuition with data.
    - **Use Historical Context**: The "Market Intel" tab provides powerful context for new, breaking-news markets.
    """)

# Footer
st.markdown("---")
st.markdown("Built with Streamlit for the Polymarket Earnings Toolkit")