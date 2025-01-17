from flask import Flask, request, render_template_string
from whoosh import index
from whoosh.qparser import QueryParser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from whoosh.fields import Schema, TEXT, ID
import os

class WebCrawler:
    def __init__(self, start_url):
        self.start_url = start_url
        self.visited = set()  # Set to track visited URLs
        self.base_netloc = urlparse(start_url).netloc  # Base domain to stay within

        # Set up the Whoosh schema and index
        schema = Schema(url=ID(stored=True, unique=True),
                        title=TEXT(stored=True),
                        teaser=TEXT(stored=True),
                        content=TEXT)
        if not os.path.exists("index"):
            os.mkdir("index")
            self.ix = index.create_in("index", schema)
        else:
            self.ix = index.open_dir("index")

    def crawl(self):
        agenda = [self.start_url]  # List to manage URLs to visit
        limit = 0

        while agenda and limit < 10:
            url = agenda.pop()  # Take the next URL to process
            if url in self.visited:
                continue  # Skip already visited URLs

            print(f"Crawling: {url}")
            limit += 1
            try:
                response = requests.get(url)
            except requests.RequestException as e:
                print(f"Failed to fetch {url}: {e}")
                continue

            # Only process successful HTML responses
            if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
                self.visited.add(url)
                soup = BeautifulSoup(response.content, 'html.parser')

                # Extract title and teaser (first 200 characters of text)
                title = soup.title.string if soup.title else "No Title"
                text_content = soup.get_text()
                teaser = text_content[:200].replace('\n', ' ').strip()

                self.index_page(url, title, teaser, text_content)  # Index the page

                # Extract and enqueue all internal links
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href'])
                    if self.is_internal_url(full_url) and full_url not in self.visited:
                        agenda.append(full_url)

    def is_internal_url(self, url):
        """Check if a URL belongs to the same server (base domain)."""
        return urlparse(url).netloc == self.base_netloc

    def index_page(self, url, title, teaser, text):
        """Index the title, teaser, and content of a page."""
        writer = self.ix.writer()
        writer.update_document(url=url, title=title, teaser=teaser, content=text)
        writer.commit()



app = Flask(__name__)

HOME_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <link rel="icon" type="image/png" href="https://cdn-icons-png.flaticon.com/128/751/751463.png">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Engine</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f9f9f9;
            color: #333;
        }
        header {
            background-color: #4CAF50;
            color: white;
            padding: 20px;
            text-align: center;
        }
        main {
            padding: 20px;
        }
        form {
            max-width: 500px;
            margin: 20px auto;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        input[type="text"] {
            width: calc(100% - 20px);
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background-color: #45a049;
        }
    </style>
</head>
<body>
    <header>
        <h1>Welcome to the Search Engine</h1>
    </header>
    <main>
        <form action="/search" method="get">
            <label for="q">Enter your search query:</label><br>
            <input type="text" id="q" name="q" placeholder="Type something..." required>
            <button type="submit">Search</button>
        </form>
    </main>
</body>
</html>
'''

RESULTS_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <link rel="icon" type="image/png" href="https://cdn-icons-png.flaticon.com/128/751/751463.png">

    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Results</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f9f9f9;
            color: #333;
        }
        header {
            background-color: #4CAF50;
            color: white;
            padding: 20px;
            text-align: center;
        }
        main {
            padding: 20px;
        }
        .result {
            margin-bottom: 15px;
            padding: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .result a {
            color: #4CAF50;
            font-size: 18px;
            font-weight: bold;
            text-decoration: none;
        }
        .result a:hover {
            text-decoration: underline;
        }
        .teaser {
            font-size: 14px;
            color: #555;
        }
        .no-results {
            text-align: center;
            margin-top: 20px;
        }
        .back {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 15px;
            background-color: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }
        .back:hover {
            background-color: #45a049;
        }
    </style>
</head>
<body>
    <header>
        <h1>Search Results</h1>
    </header>
    <main>
        {% if results %}
            {% for url, title, teaser in results %}
                <div class="result">
                    <a href="{{ url }}" target="_blank">{{ title }}</a>
                    <p class="teaser">{{ teaser }}</p>
                </div>
            {% endfor %}
        {% else %}
            <p class="no-results">No results or too many found for your query.</p>
        {% endif %}
        <a href="/" class="back">Back to Home</a>
    </main>
</body>
</html>
'''

@app.route('/')
def home():
    return HOME_PAGE

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()  # Extract the search query
    if not query:
        return "Please enter a search query."

    try:
        ix = index.open_dir("index")  # Open the Whoosh index and search for the query
        results = []
        with ix.searcher() as searcher:
            qp = QueryParser("content", schema=ix.schema)
            q = qp.parse(query)
            hits = searcher.search(q, limit=None)
            results = list(set((hit["url"], hit["title"], hit["teaser"]) for hit in hits))  # Collect unique results

        return render_template_string(RESULTS_PAGE, results=results)
    except Exception as e:
        return f"Error: {e}"




# Run the Flask app
if __name__ == "__main__":
    start_url = "https://vm009.rz.uos.de/crawl/index.html"  # Paste URL here
    crawler = WebCrawler(start_url)
    crawler.crawl()
    print("Crawling complete. Starting Flask app...")
    app.run(debug=True)