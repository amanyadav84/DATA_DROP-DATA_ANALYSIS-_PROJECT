# Data Drop

**Enterprise Analytics Platform** — Upload, analyze, visualize, and share your data with AI-powered insights.

---

## Features

- **Multi-Dataset Workspace** — Upload and manage multiple datasets. Merge, join, and analyze them together.
- **28+ Interactive Chart Types** — Histograms, scatter plots, bar charts, box plots, heatmaps, and more with smart suggestions.
- **AI-Powered Insights** — Automated data quality analysis, anomaly detection, and business recommendations.
- **Dashboard Builder** — Drag-and-drop dashboard creation with templates and presentation mode.
- **Advanced Data Cleaning** — Fill nulls, drop duplicates, normalize text, detect and treat outliers, auto-clean.
- **Correlation & Distribution Analysis** — Pearson/Spearman correlation, distribution charts, and statistical tests.
- **Feature Engineering** — Encoding, scaling, transforms, date features, polynomial features, and more.
- **Natural Language Querying** — Ask questions about your data in plain English.
- **EDA Report Generator** — Full, quick, technical, business, and executive report types.
- **Chunked Upload** — Supports files up to 5 GB with resume capability.

## Tech Stack

| Layer     | Technology                        |
| --------- | --------------------------------- |
| Backend   | Python, FastAPI, Uvicorn          |
| Frontend  | HTML, CSS, JavaScript, Plotly.js  |
| Data      | Pandas, NumPy, SciPy, scikit-learn|
| AI/ML     | Google Generative AI (optional)   |

## Project Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Environment configuration
│   ├── session.py              # Session management
│   ├── processor.py            # Data profiling and preview
│   ├── charts.py               # Chart generation
│   ├── cleaner.py              # Data cleaning operations
│   ├── correlation.py          # Correlation analysis
│   ├── distribution.py         # Distribution analysis
│   ├── quality_report.py       # Dataset quality reports
│   ├── ai_service.py           # AI integration service
│   ├── ai_insights_engine.py   # AI insights generation
│   ├── eda_report.py           # EDA report generation
│   ├── nlq_engine.py           # Natural language querying
│   ├── feature_engineering.py  # Feature engineering tools
│   ├── statistical_tests.py    # Statistical hypothesis testing
│   ├── sql_generator.py        # SQL query generation
│   ├── code_generator.py       # Python code generation
│   ├── chart_advisor.py        # AI chart recommendations
│   ├── dashboard.py            # Dashboard builder backend
│   ├── project.py              # Project management
│   ├── chunked_upload.py       # Large file upload handling
│   ├── report_template.py      # HTML report templates
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Environment variables (not committed)
├── frontend/
│   ├── index.html              # Main SPA entry point
│   ├── styles.css              # Application styles
│   └── app.js                  # Frontend application logic
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- **Python 3.10+**
- **pip** (Python package manager)

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/data-drop.git
   cd data-drop
   ```

2. **Create and activate a virtual environment**

   ```bash
   cd backend
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables** (optional)

   Create a `.env` file in the `backend/` directory:

   ```env
   AI_STUDIO_API_KEY=your_api_key_here
   AI_STUDIO_BASE_URL=https://generativelanguage.googleapis.com/v1beta
   ```

5. **Start the server**

   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

6. **Open the application**

   Navigate to [http://localhost:8000](http://localhost:8000) in your browser.

### Environment Variables

| Variable                        | Default                                                    | Description                        |
| ------------------------------- | ---------------------------------------------------------- | ---------------------------------- |
| `AI_STUDIO_API_KEY`             | `""`                                                       | API key for AI features            |
| `AI_STUDIO_BASE_URL`            | `https://generativelanguage.googleapis.com/v1beta`          | AI service base URL                |
| `UPLOAD_LIMIT_CSV_MB`           | `2048`                                                     | Max CSV upload size (MB)           |
| `UPLOAD_LIMIT_JSON_MB`          | `1024`                                                     | Max JSON upload size (MB)          |
| `UPLOAD_LIMIT_XLSX_MB`          | `512`                                                      | Max Excel upload size (MB)         |
| `UPLOAD_LIMIT_PARQUET_MB`       | `5120`                                                     | Max Parquet upload size (MB)       |
| `MAX_UPLOAD_MB`                 | `5120`                                                     | Absolute max upload size (MB)      |
| `CHUNK_SIZE_BYTES`              | `5242880`                                                  | Chunk size for resumable uploads   |
| `LARGE_FILE_WARNING_MB`         | `1024`                                                     | Threshold for large file warning   |
| `STREAMING_THRESHOLD_MB`        | `100`                                                      | Threshold for streaming processing |

## API Documentation

Once the server is running, visit:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Usage

1. **Upload Data** — Drag and drop CSV, JSON, TSV, XLSX, or Parquet files onto the upload zone.
2. **Explore** — View data profiles, column statistics, and smart chart suggestions.
3. **Analyze** — Run correlation analysis, distribution analysis, and statistical tests.
4. **Clean** — Apply cleaning operations like filling nulls, dropping duplicates, or auto-clean.
5. **Visualize** — Build interactive charts and dashboards.
6. **AI Insights** — Generate automated insights and recommendations.
7. **Ask Data** — Query your dataset using natural language.
8. **Export** — Download cleaned data, charts, reports, and dashboards in multiple formats.

## Supported File Formats

| Format    | Extension | Max Size   |
| --------- | --------- | ---------- |
| CSV       | `.csv`    | 2 GB       |
| JSON      | `.json`   | 1 GB       |
| TSV       | `.tsv`    | 2 GB       |
| Text      | `.txt`    | 2 GB       |
| Excel     | `.xlsx`   | 500 MB     |
| Parquet   | `.parquet`| 5 GB       |

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome. Please open an issue or submit a pull request.
