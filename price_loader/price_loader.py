from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Price Loader Service")


def run():
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Price Loader service running on port 8000")
    server.serve_forever()


if __name__ == "__main__":
    run()
