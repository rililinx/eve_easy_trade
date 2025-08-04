from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Jump Graph Service")


def run():
    server = HTTPServer(("0.0.0.0", 8002), Handler)
    print("Jump Graph service running on port 8002")
    server.serve_forever()


if __name__ == "__main__":
    run()
