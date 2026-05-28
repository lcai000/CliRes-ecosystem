import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from io import BytesIO
import warnings

# --- Import from your own project files ---
from helpers.config import *
from helpers.utils import get_base_col_name
from helpers.data_processing import filter_dataframe, aggregate_dataframe, standardize_dataframe

# --- HELPER FUNCTIONS SPECIFIC TO THIS GRAPHING PAGE ---

def get_graphing_configs(df):
    """Creates the UI widgets for configuring the graph."""
    st.subheader("Graphing Options")
    configs = {}
    col1, col2 = st.columns(2)
    configs['aggregation_level'] = col1.selectbox("Select Time Granularity:", ["5-minute (Raw)", "Hourly", "Daily", "Weekly", "Monthly"], index=0)
    if configs['aggregation_level'] != "5-minute (Raw)":
        configs['aggregation_method'] = col2.selectbox("Select Display Method:", ["Mean (Average)", "Minimum", "Maximum", "Mean with Min/Max Range"], index=0)
    else: 
        configs['aggregation_method'] = "Mean (Average)"
    
    if COL_PLANT_NAME in df.columns:
        configs['plot_overall_average'] = st.checkbox("Plot overall average across all plants")
        if not configs['plot_overall_average']:
            available_plants = df[COL_PLANT_NAME].unique().tolist()
            configs['selected_plants'] = st.multiselect("Select Plant Names:", available_plants, default=available_plants)
            
            # --- Grouping Option ---
            configs['group_by_pattern'] = st.checkbox("Group plants by name pattern (e.g. 'Biochar' vs 'Control')")
            if configs['group_by_pattern']:
                default_patterns = "Control Elm, Redbud, Chinquapin"
                configs['group_patterns'] = st.text_input("Enter patterns separated by comma:", value=default_patterns, help="Plants containing these words will be averaged together into groups.")

            # --- Facet vs Overlay Option ---
            layout_choice = st.radio(
                "Graph Layout:", 
                ["Separate Graphs (Side-by-Side)", "Combined Graph (Overlaid Lines)"],
                index=1, 
                horizontal=True
            )
            configs['use_facets'] = (layout_choice == "Separate Graphs (Side-by-Side)")
            
            # --- Data Cleaning ---
            st.caption("Data Cleaning:")
            
            # 1. Filter Zeros
            configs['filter_zeros'] = st.checkbox("Exclude invalid/zero readings", value=False)
            if configs['filter_zeros']:
                configs['min_val'] = st.number_input(
                    "Minimum valid value (microns):", 
                    value=100, 
                    help="Readings below this value will be removed BEFORE analysis."
                )
            
            # 2. Auto-Stitch (Corrects vertical jumps)
            configs['auto_stitch'] = st.checkbox("Auto-Stitch: Fix vertical sensor jumps/resets", help="Detects large sudden drops/jumps and shifts the data to make the line continuous.")
            if configs['auto_stitch']:
                configs['jump_threshold'] = st.number_input(
                    "Jump Threshold (microns):", 
                    value=1000, 
                    step=100,
                    help="If the jump between two plotted points is larger than this, it is treated as a sensor reset."
                )

            # --- Standardization Option ---
            st.caption("Advanced Analysis:")
            configs['normalization_mode'] = st.selectbox(
                "Standardize Data:",
                ["None (Raw Data)", "% Deviation from Mean", "Change from Start (Zero-Indexed)"],
                help="Choose how to normalize the data for comparison."
            )
            
    return configs

def _plot_trendline(ax, x_data, y_data, **kwargs):
    """Helper to draw a trendline on a plot."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.RankWarning)
        valid_indices = pd.Series(y_data).notna() & pd.Series(x_data).notna()
        x_valid, y_valid = x_data[valid_indices], y_data[valid_indices]
        if len(x_valid) < 2: return
        try:
            x_numeric = x_valid.astype(np.int64) // 10**9 if pd.api.types.is_datetime64_any_dtype(x_valid) else x_valid
            coeffs = np.polyfit(x_numeric, y_valid, 1)
            trend_fn = np.poly1d(coeffs)
            ax.plot(x_valid, trend_fn(x_numeric), **kwargs)
        except Exception: pass

def _plot_trendline_on_facet(data, x, y, **kwargs):
    """Adapter function to draw trendlines on faceted Seaborn plots."""
    ax = plt.gca()
    _plot_trendline(ax, data[x], data[y], **kwargs)

def create_plot(df, x_col, y_col, plot_type, title, x_label, y_label, configs):
    """Main function to create either a single or faceted plot."""
    sns.set_theme(style="whitegrid")
    df = df.copy()
    
    if df.empty:
        st.warning("The data is empty after processing. Cannot create a plot.")
        return None
    
    # Ensure the Plant Name column is a string type before sorting.
    if COL_PLANT_NAME in df.columns:
        df[COL_PLANT_NAME] = df[COL_PLANT_NAME].astype(str)

    # --- Timezone Standardization ---
    if x_col == COL_TIMESTAMP:
        st.write("Standardizing timezones for plotting...")
        df[x_col] = pd.to_datetime(df[x_col], errors='coerce', utc=True).dt.tz_localize(None)
        df.dropna(subset=[x_col], inplace=True)
        
    plot_individual = COL_PLANT_NAME in df.columns and not configs.get('plot_overall_average', False)
    num_groups = df[COL_PLANT_NAME].nunique() if plot_individual else 0

    # 1. Single Plot (Overall Average or Single Plant/Group)
    if not plot_individual or num_groups <= 1:
        fig, ax = plt.subplots(figsize=(10, 6))
        plot_func = ax.plot if plot_type == "Line Plot" else ax.scatter if plot_type == "Scatter Plot" else ax.bar
        df_sorted = df.sort_values(by=x_col, ignore_index=True)
        
        # Draw the main plot
        if plot_type == "Line Plot":
            # If they force a line plot on non-time data, avoid drawing multiple overlapping lines
            sns.lineplot(data=df_sorted, x=x_col, y=y_col, ax=ax, errorbar=None)
        else:
            plot_func(df_sorted[x_col], df_sorted[y_col], alpha=0.6) # add slight transparency to scatter points
            
        if plot_type in ["Line Plot", "Scatter Plot"]:
            _plot_trendline(ax, df_sorted[x_col].values, df_sorted[y_col].values, **TRENDLINE_STYLE, label='Trend')
            ax.legend()
            
        ax.set_title(title, fontsize=16)
        ax.set_ylabel(y_label, fontsize=12)
        ax.set_xlabel(x_label, fontsize=12)
        ax.grid(True)
        if pd.api.types.is_datetime64_any_dtype(df[x_col]): 
            fig.autofmt_xdate(rotation=45)
            ax.tick_params(axis='x', rotation=45)
        plt.tight_layout()
        return fig
    
    else: # Multiple Groups/Plants Selected
        df_sorted = df.sort_values(by=[COL_PLANT_NAME, x_col])
        
        # --- Option A: Faceted Plots (Side-by-Side) ---
        if configs.get('use_facets', False): 
            if plot_type in ["Line Plot", "Scatter Plot"]:
                kind_arg = "line" if plot_type == "Line Plot" else "scatter"
                
                # Setup kwargs specifically for the plot kind to prevent messiness
                facet_kwargs = {
                    'data': df_sorted, 'x': x_col, 'y': y_col, 
                    'col': COL_PLANT_NAME, 'hue': COL_PLANT_NAME, 
                    'kind': kind_arg, 'height': 5, 'aspect': 1.2, 
                    'col_wrap': 3, 'palette': 'tab10',
                    'facet_kws': {'sharey': False, 'sharex': True}
                }
                if kind_arg == "line":
                    facet_kwargs['errorbar'] = None # Fixes blurry bands when lines overlap
                elif kind_arg == "scatter":
                    facet_kwargs['alpha'] = 0.6
                
                g = sns.relplot(**facet_kwargs)
                g.map_dataframe(_plot_trendline_on_facet, x=x_col, y=y_col, **TRENDLINE_STYLE)
                g.fig.suptitle(title, y=1.03, fontsize=16)
                g.set_axis_labels(x_label, y_label)
                g.set_titles(col_template="{col_name}")
                
                if pd.api.types.is_datetime64_any_dtype(df[x_col]):
                    for ax in g.axes.flat:
                        for label in ax.get_xticklabels():
                            label.set_rotation(45)
                            label.set_horizontalalignment('right')

                plt.tight_layout(rect=[0, 0, 1, 0.97])
                return g.fig
            
            elif plot_type == "Bar Plot":
                plants = df_sorted[COL_PLANT_NAME].unique()
                n_cols = 3
                n_rows = (len(plants) + n_cols - 1) // n_cols
                fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5, n_rows * 4), sharex=True, sharey=False)
                axes = axes.flatten()
                cmap = plt.get_cmap('tab10')
                for i, plant in enumerate(plants):
                    ax = axes[i]
                    plant_data = df_sorted[df_sorted[COL_PLANT_NAME] == plant]
                    color = cmap(i % 10)
                    ax.bar(plant_data[x_col], plant_data[y_col], color=color)
                    ax.set_title(plant)
                    ax.grid(True)
                    ax.tick_params(axis='x', rotation=45) 
                    
                    if i < (n_rows - 1) * n_cols:
                        plt.setp(ax.get_xticklabels(), visible=False)

                for j in range(i + 1, len(axes)): axes[j].set_visible(False)
                fig.suptitle(title, fontsize=16)
                plt.tight_layout(rect=[0, 0, 1, 0.96])
                return fig

        # --- Option B: Overlaid Plots (Same Graph) ---
        else:
            fig, ax = plt.subplots(figsize=(12, 6))
            
            if plot_type == "Line Plot":
                # errorbar=None removes the messy shading around lines
                sns.lineplot(data=df_sorted, x=x_col, y=y_col, hue=COL_PLANT_NAME, ax=ax, errorbar=None)
            elif plot_type == "Scatter Plot":
                sns.scatterplot(data=df_sorted, x=x_col, y=y_col, hue=COL_PLANT_NAME, ax=ax, alpha=0.6)
            elif plot_type == "Bar Plot":
                sns.barplot(data=df_sorted, x=x_col, y=y_col, hue=COL_PLANT_NAME, ax=ax, errorbar=None)
            
            ax.set_title(title, fontsize=16)
            ax.set_ylabel(y_label, fontsize=12)
            ax.set_xlabel(x_label, fontsize=12)
            ax.grid(True)
            if pd.api.types.is_datetime64_any_dtype(df[x_col]): 
                fig.autofmt_xdate(rotation=45)
                ax.tick_params(axis='x', rotation=45)
            plt.tight_layout()
            return fig

# --- MAIN PAGE LOGIC ---

def graph_main():
    st.header("📊 Build Custom Graphs")
    st.write("This tool uses any data loaded from the API or from local file uploads on the Home page.")
    st.info("Note: for Certain Data (e.g., Kestrel, LCRA), Ensure the Time Granularity is At Least Hourly for Meaningful Graphs.")

    # 1. Combine all available data from session state
    data_to_combine = []
    
    if 'combined_df' in st.session_state and not st.session_state['combined_df'].empty:
        raw_combined_df = st.session_state['combined_df']
    else:
        # Fallback to rebuilding it
        if 'api_df' in st.session_state:
            data_to_combine.append(st.session_state.api_df)
        if 'kestrel_df' in st.session_state:
            data_to_combine.append(st.session_state.kestrel_df)
        if 'lcra_df' in st.session_state:
            data_to_combine.append(st.session_state.lcra_df)

        if not data_to_combine:
            st.info("Please load data on the main `app.py` Home page to begin.")
            st.stop()
            
        raw_combined_df = pd.concat(data_to_combine, ignore_index=True)

    # 2. Clean and standardize the data
    st.write("⚙️ Standardizing data...")
    combined_df = standardize_dataframe(raw_combined_df)

    if combined_df.empty:
        st.error("Data is empty after standardization. Please check file formats.")
        st.stop()

    # 3. Display UI and process data
    st.subheader("Data Overview (Combined)")
    st.dataframe(combined_df.head())

    configs = get_graphing_configs(combined_df)
    if 'start_date' in st.session_state:
        configs['start_date'] = st.session_state.start_date
        configs['end_date'] = st.session_state.end_date

    # --- FILTER DATA ---
    filtered_df = filter_dataframe(combined_df, configs, COL_TIMESTAMP)
    
    # --- STEP A: Apply Data Cleaning (Filter Zeros) ---
    if configs.get('filter_zeros'):
        dendro_col = "Dendrometer (microns)"
        if dendro_col in filtered_df.columns:
            original_count = len(filtered_df)
            filtered_df = filtered_df[filtered_df[dendro_col] >= configs['min_val']]
            dropped = original_count - len(filtered_df)
            if dropped > 0:
                st.info(f"🧹 Cleaned data: Removed {dropped} rows with values below {configs['min_val']} microns.")

    # --- STEP B: Apply Pattern Grouping BEFORE Aggregation ---
    if configs.get('group_by_pattern') and configs.get('group_patterns'):
        patterns = [p.strip() for p in configs['group_patterns'].split(',') if p.strip()]
        
        def assign_group(name):
            for p in patterns:
                if p.lower() in name.lower():
                    return p 
            return "Other" 
        
        unique_plants = filtered_df[COL_PLANT_NAME].unique()
        group_map = {name: assign_group(name) for name in unique_plants}
        filtered_df[COL_PLANT_NAME] = filtered_df[COL_PLANT_NAME].map(group_map)
        
        st.info(f"Grouping active: Plants grouped into {patterns + ['Other']}")

    # --- STEP C: Aggregate Data First ---
    # This smooths out the 5-minute wiggles into Hourly/Daily averages
    data_to_plot = aggregate_dataframe(filtered_df, configs, COL_TIMESTAMP)

    if data_to_plot.empty:
        st.warning("No data remains after filtering and aggregation. Please adjust your settings.")
        st.stop()

    # --- STEP D: Auto-Stitch / Jump Correction (Applied to the Aggregated View) ---
    if configs.get('auto_stitch'):
        dendro_col = "Dendrometer (microns)"
        threshold = configs.get('jump_threshold', 1000)
        
        if dendro_col in data_to_plot.columns:
            try:
                data_to_plot = data_to_plot.sort_values(by=[COL_PLANT_NAME, COL_TIMESTAMP]).copy()
                diffs = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform(lambda x: x.ffill().diff()).fillna(0)
                jumps = diffs.where(diffs.abs() > threshold, 0)
                adjustments = jumps.groupby(data_to_plot[COL_PLANT_NAME]).cumsum()
                data_to_plot[dendro_col] = data_to_plot[dendro_col] - adjustments
                st.success(f"✂️ Auto-Stitched data: Corrected jumps larger than {threshold} microns on the aggregated view.")
            except Exception as e:
                st.error(f"Error during auto-stitching: {e}")

    # --- STEP E: Perform Normalization Calculation (After Stitching!) ---
    norm_mode = configs.get('normalization_mode', "None (Raw Data)")
    
    if norm_mode == "% Deviation from Mean":
        dendro_col = "Dendrometer (microns)"
        if dendro_col in data_to_plot.columns:
            plant_means = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform('mean')
            new_col_name = "Dendrometer (% Deviation)"
            data_to_plot[new_col_name] = ((data_to_plot[dendro_col] - plant_means) / plant_means) * 100
            st.success(f"Calculated '{new_col_name}'!")
            
    elif norm_mode == "Change from Start (Zero-Indexed)":
        dendro_col = "Dendrometer (microns)"
        if dendro_col in data_to_plot.columns:
            def zero_index(group):
                valid_group = group.dropna()
                if valid_group.empty: return group
                first_val = valid_group.iloc[0]
                return group - first_val
            
            new_col_name = "Dendrometer (Change from Start)"
            data_to_plot[new_col_name] = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform(zero_index)
            st.success(f"Calculated '{new_col_name}'!")


    # 4. Get user selections for plotting
    st.subheader("Select Plot Variables")
    axis_options = data_to_plot.columns.tolist()
    
    # We use columns to layout the dropdowns cleanly
    col1, col2 = st.columns(2)
    
    with col1:
        # 1. SELECT X-AXIS FIRST
        x_axis_col = st.selectbox("Select X-axis:", [opt for opt in axis_options if opt != COL_PLANT_NAME])
        
        # 2. APPLY X-AXIS BINNING (Robust mathematical grouping for scatter/trend graphs)
        is_binned = False
        if pd.api.types.is_numeric_dtype(data_to_plot[x_axis_col]) and x_axis_col != COL_TIMESTAMP:
            st.info(f"💡 Grouping {x_axis_col} automatically cleans up the graph.")
            # Set value=True so it automatically fixes the messy graph
            if st.checkbox(f"Enable Binning for {x_axis_col}", value=True, help="Groups the X-axis into buckets to create a clean, single trend line."):
                is_binned = True
                bin_size = st.number_input(f"Bin Size for {x_axis_col}:", value=2.0, step=0.5, min_value=0.1)
                
                # Robust mathematical binning
                binned_col_name = f"{x_axis_col} (Binned)"
                data_to_plot[binned_col_name] = np.floor(data_to_plot[x_axis_col] / bin_size) * bin_size
                
                # Group safely depending on whether COL_PLANT_NAME is present
                group_cols = [binned_col_name]
                if COL_PLANT_NAME in data_to_plot.columns:
                    group_cols.insert(0, COL_PLANT_NAME)
                    
                data_to_plot = data_to_plot.groupby(group_cols).mean(numeric_only=True).reset_index()
                data_to_plot.dropna(subset=[binned_col_name], inplace=True)
                x_axis_col = binned_col_name 

    with col2:
        # 3. SELECT Y-AXIS
        y_options = [c for c in data_to_plot.select_dtypes(include=np.number).columns if c not in [x_axis_col, COL_PLANT_NAME]]
        
        # Auto-select the normalized column if available
        default_y_index = 0
        if norm_mode != "None (Raw Data)":
            target_keyword = "Deviation" if "Deviation" in norm_mode else "Change"
            dev_cols = [i for i, c in enumerate(y_options) if target_keyword in c]
            if dev_cols:
                default_y_index = dev_cols[0]
                
        if not y_options: 
            st.error("Not enough numerical columns for Y-axis.")
            st.stop()
            
        y_axis_col = st.selectbox("Select Y-axis:", y_options, index=default_y_index)
        
    # --- SMART PLOT DEFAULTING ---
    # If the X-axis is a timeline OR it has been binned into neat buckets, default to Line Plot.
    # Otherwise, default to Scatter Plot to avoid the scribble effect.
    default_plot_type_idx = 0 if (x_axis_col == COL_TIMESTAMP or is_binned) else 1
    
    # REMOVED `key='plot_type'` so Streamlit respects the dynamic index change automatically!
    plot_type = st.selectbox(
        "Select Plot Type:", 
        ["Line Plot", "Scatter Plot", "Bar Plot"], 
        index=default_plot_type_idx, 
        help="Use a Scatter Plot when comparing raw environmental variables to avoid messy, connected lines."
    )

    # 5. Get plot customizations
    st.subheader("Customize Plot Appearance")
    y_axis_base_name = get_base_col_name(y_axis_col)
    title = st.text_input("Plot Title:", f"{y_axis_base_name} vs. {get_base_col_name(x_axis_col)}")
    x_label = st.text_input("X-axis Label:", get_base_col_name(x_axis_col))
    y_label = st.text_input("Y-axis Label:", y_axis_base_name)
    

    # --- UNIVERSAL Y-AXIS SMOOTHING (Only allow this if X-Axis is Time) ---
    if x_axis_col == COL_TIMESTAMP:
        smooth_window = st.slider(
            "Smooth Y-Axis (Rolling Average Window)", 
            min_value=1, max_value=100, value=1, 
            help="Slide this to the right to smooth out jagged spikes and noise in the timeline."
        )
        if smooth_window > 1:
            if COL_PLANT_NAME in data_to_plot.columns:
                data_to_plot[y_axis_col] = data_to_plot.groupby(COL_PLANT_NAME)[y_axis_col].transform(lambda x: x.rolling(smooth_window, min_periods=1).mean())
            else:
                data_to_plot[y_axis_col] = data_to_plot[y_axis_col].rolling(smooth_window, min_periods=1).mean()
            st.success(f"Applied a {smooth_window}-point rolling average to smooth the Y-Axis line.")

    # 6. Generate the graph
    if st.button("Generate Graph", type="primary"):
        fig = create_plot(data_to_plot, x_axis_col, y_axis_col, plot_type, title, x_label, y_label, configs)
        
        if fig:
            # ---DYNAMIC GROWTH METRIC ---
            # Only trigger this if we are looking at dendrometry over time!
            if "Dendrometer" in y_axis_col and x_axis_col == COL_TIMESTAMP:
                st.markdown("### 🌲 Net Growth Analysis")
                
                # Check if we have multiple plants plotted
                if COL_PLANT_NAME in data_to_plot.columns:
                    unique_plants = data_to_plot[COL_PLANT_NAME].unique()
                    # Create a neat row of columns for the metrics
                    metric_cols = st.columns(len(unique_plants))
                    
                    for i, plant in enumerate(unique_plants):
                        plant_data = data_to_plot[data_to_plot[COL_PLANT_NAME] == plant].sort_values(by=COL_TIMESTAMP)
                        if not plant_data.empty:
                            first_val = plant_data[y_axis_col].iloc[0]
                            last_val = plant_data[y_axis_col].iloc[-1]
                            net_growth = last_val - first_val
                            
                            with metric_cols[i]:
                                st.metric(
                                    label=f"{plant}", 
                                    value=f"{last_val:.1f} µm", 
                                    delta=f"{net_growth:.1f} µm"
                                )
                else:
                    # If it's just one overall average line
                    sorted_data = data_to_plot.sort_values(by=COL_TIMESTAMP)
                    if not sorted_data.empty:
                        first_val = sorted_data[y_axis_col].iloc[0]
                        last_val = sorted_data[y_axis_col].iloc[-1]
                        net_growth = last_val - first_val
                        
                        st.metric(
                            label="Overall Average Growth", 
                            value=f"{last_val:.1f} µm", 
                            delta=f"{net_growth:.1f} µm"
                        )
                st.divider() # Draw a clean line before the graph
            # ----------------------------------
            
            # Draw the graph (using our anti-stretch fix!)
            st.pyplot(fig, use_container_width=False)
            
            # Helper text for anomalies
            st.info(
                "**Interpreting Anomalies:** If you see large vertical jumps or drops, "
                "this usually indicates the sensor was moved or reset. The daily patterns (small wiggles) "
                "before and after the jump remain valid for analysis. "
                "Use the 'Auto-Stitch' option above to smooth these out."
            )

            # Dynamic Filename
            safe_title = "".join(x for x in title if x.isalnum() or x in "._- ")
            safe_title = safe_title.replace(" ", "_")
            if not safe_title: safe_title = "plot"

            buf = BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=300)
            st.download_button("Download Plot as PNG", data=buf, file_name=f"{safe_title}.png", mime="image/png")
            
            buf_pdf = BytesIO()
            fig.savefig(buf_pdf, format='pdf', bbox_inches='tight')
            st.download_button("Download Plot as PDF", data=buf_pdf, file_name=f"{safe_title}.pdf", mime="application/pdf")
            plt.close(fig) # Close the figure to free memory

graph_main()