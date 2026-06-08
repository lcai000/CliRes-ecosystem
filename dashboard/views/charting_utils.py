import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
import warnings
import base64
from io import BytesIO

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME, TRENDLINE_STYLE
from dashboard.helpers.utils import get_base_col_name


def fig_to_b64(fig):
    """Convert a matplotlib Figure to a base64 data URI string."""
    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return f"data:image/png;base64,{b64}"


def fig_to_png_bytes(fig):
    """Convert a matplotlib Figure to PNG bytes for download."""
    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=300)
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def _plot_trendline(ax, x_data, y_data, **kwargs):
    """Helper to draw a trendline on a plot."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.RankWarning)
        valid_indices = pd.Series(y_data).notna() & pd.Series(x_data).notna()
        x_valid, y_valid = x_data[valid_indices], y_data[valid_indices]
        if len(x_valid) < 2:
            return
        try:
            x_numeric = x_valid.astype(np.int64) // 10**9 if pd.api.types.is_datetime64_any_dtype(x_valid) else x_valid
            coeffs = np.polyfit(x_numeric, y_valid, 1)
            trend_fn = np.poly1d(coeffs)
            ax.plot(x_valid, trend_fn(x_numeric), **kwargs)
        except Exception:
            pass


def _plot_trendline_on_facet(data, x, y, **kwargs):
    ax = plt.gca()
    _plot_trendline(ax, data[x], data[y], **kwargs)


def create_plot(df, x_col, y_col, plot_type, title, x_label, y_label, configs):
    """Main function to create either a single or faceted plot."""
    sns.set_theme(style="whitegrid")
    df = df.copy()

    if df.empty:
        return None

    if COL_PLANT_NAME in df.columns:
        df[COL_PLANT_NAME] = df[COL_PLANT_NAME].astype(str)

    if x_col == COL_TIMESTAMP:
        df[x_col] = pd.to_datetime(df[x_col], errors='coerce', utc=True).dt.tz_localize(None)
        df.dropna(subset=[x_col], inplace=True)

    plot_individual = COL_PLANT_NAME in df.columns and not configs.get('plot_overall_average', False)
    num_groups = df[COL_PLANT_NAME].nunique() if plot_individual else 0

    # Single Plot
    if not plot_individual or num_groups <= 1:
        fig, ax = plt.subplots(figsize=(10, 6))
        df_sorted = df.sort_values(by=x_col, ignore_index=True)

        if plot_type == "Line Plot":
            sns.lineplot(data=df_sorted, x=x_col, y=y_col, ax=ax, errorbar=None)
        elif plot_type == "Scatter Plot":
            ax.scatter(df_sorted[x_col], df_sorted[y_col], alpha=0.6)
        else:
            ax.bar(df_sorted[x_col].astype(str), df_sorted[y_col])

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

    # Multiple Groups
    else:
        df_sorted = df.sort_values(by=[COL_PLANT_NAME, x_col])

        if configs.get('use_facets', False):
            if plot_type in ["Line Plot", "Scatter Plot"]:
                kind_arg = "line" if plot_type == "Line Plot" else "scatter"
                facet_kwargs = {
                    'data': df_sorted, 'x': x_col, 'y': y_col,
                    'col': COL_PLANT_NAME, 'hue': COL_PLANT_NAME,
                    'kind': kind_arg, 'height': 5, 'aspect': 1.2,
                    'col_wrap': 3, 'palette': 'tab10',
                    'facet_kws': {'sharey': False, 'sharex': True}
                }
                if kind_arg == "line":
                    facet_kwargs['errorbar'] = None
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
                axes = np.atleast_1d(axes).flatten()
                cmap = plt.get_cmap('tab10')
                for i, plant in enumerate(plants):
                    ax = axes[i]
                    plant_data = df_sorted[df_sorted[COL_PLANT_NAME] == plant]
                    color = cmap(i % 10)
                    ax.bar(plant_data[x_col].astype(str), plant_data[y_col], color=color)
                    ax.set_title(plant)
                    ax.grid(True)
                    ax.tick_params(axis='x', rotation=45)
                for j in range(i + 1, len(axes)):
                    axes[j].set_visible(False)
                fig.suptitle(title, fontsize=16)
                plt.tight_layout(rect=[0, 0, 1, 0.96])
                return fig

        # Overlaid
        else:
            fig, ax = plt.subplots(figsize=(12, 6))
            if plot_type == "Line Plot":
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
