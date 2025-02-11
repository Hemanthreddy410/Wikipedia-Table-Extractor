from flask import Flask, render_template, request, send_file, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import re
from io import BytesIO

app = Flask(__name__)
UPLOAD_FOLDER = "downloads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def sanitize_filename(name):
    """Remove invalid characters from filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).replace(' ', '_') 

def clean_text(text):
    """Remove [note] and [number] references from extracted text."""
    return re.sub(r'\[.*?\]', '', text).strip()

def make_headers_unique(headers):
    """Ensure headers are unique by appending numbers to duplicates."""
    seen = {}
    unique_headers = []
    for col in headers:
        if col in seen:
            seen[col] += 1
            unique_headers.append(f"{col} ({seen[col]})")
        else:
            seen[col] = 1
            unique_headers.append(col)
    return unique_headers

def fetch_wikipedia_tables(url):
    """Fetch and extract all tables from a Wikipedia page."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return {"error": f"Failed to fetch {url}. Status Code: {response.status_code}"}

        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")

        if not tables:
            return {"error": f"No tables found on {url}"}

        table_data = []
        all_dataframes = []
        headings = soup.find_all(["h2", "h3", "h4"])  # Get section headings

        for i, table in enumerate(tables):
            title = "Untitled_Table"
            for heading in reversed(headings):
                if heading.find_next("table") == table:
                    title = sanitize_filename(heading.text.strip())  # Sanitize title
                    break

            # Extract headers (handling missing headers properly)
            headers = []
            for header_row in table.find_all("tr")[:2]:  # First 2 rows could be headers
                row_headers = [clean_text(header.text.strip()) for header in header_row.find_all("th")]
                if row_headers:
                    headers = row_headers

            # Extract rows
            rows = []
            for row in table.find_all("tr")[1:]:
                cells = [clean_text(cell.text.strip()) for cell in row.find_all("td")]
                if cells:
                    rows.append(cells)

            # **Fix Header-Row Mismatch**
            if headers and rows and len(headers) != len(rows[0]):
                headers = [f"Column {j+1}" for j in range(len(rows[0]))]

            # **Ensure Headers Are Unique**
            headers = make_headers_unique(headers)

            # **Ensure DataFrame and Save CSV**
            try:
                df = pd.DataFrame(rows, columns=headers)
            except ValueError:
                print(f"Error in table '{title}': Adjusting headers dynamically.")
                max_columns = max(len(row) for row in rows)  # Get max number of columns
                headers = [f"Column {j+1}" for j in range(max_columns)]
                df = pd.DataFrame(rows, columns=headers)

            all_dataframes.append(df)

            # Save individual file
            safe_title = sanitize_filename(title)
            file_name = f"{safe_title}_table_{i+1}.csv"
            file_path = os.path.join(UPLOAD_FOLDER, file_name)
            df.to_csv(file_path, index=False)

            table_data.append({
                "title": title,
                "table_number": i + 1,
                "headers": headers,
                "table_html": df.to_html(classes="table table-bordered", index=False),
                "download_link": file_name
            })

        # Save all tables combined
        combined_file = os.path.join(UPLOAD_FOLDER, "all_tables_combined.csv")
        pd.concat(all_dataframes, ignore_index=True).to_csv(combined_file, index=False)

        return {"tables": table_data}

    except Exception as e:
        return {"error": str(e)}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        urls = request.form.get("urls").split("\n")
        all_tables = []

        for url in urls:
            url = url.strip()
            if url:
                result = fetch_wikipedia_tables(url)
                if "error" in result:
                    return render_template("index.html", error=result["error"])
                all_tables.extend(result["tables"])

        return render_template("index.html", tables=all_tables)

    return render_template("index.html", tables=[])

@app.route("/download_csv/<filename>")
def download_csv(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    return send_file(file_path, as_attachment=True)

@app.route("/download_all")
def download_all():
    """Download all tables in one CSV file."""
    file_path = os.path.join(UPLOAD_FOLDER, "all_tables_combined.csv")
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
