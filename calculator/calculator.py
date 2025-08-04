from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Calculator Service")


def run():
    server = HTTPServer(("0.0.0.0", 8001), Handler)
    print("Calculator service running on port 8001")
    server.serve_forever()


if __name__ == "__main__":
    run()
