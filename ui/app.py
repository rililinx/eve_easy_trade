from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"UI Service")


def run():
    port = 8501
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"UI service running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
