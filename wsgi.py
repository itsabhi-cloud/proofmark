import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 5050, not 5000: on macOS, port 5000 is taken by AirPlay Receiver.
    app.run(debug=True, port=int(os.environ.get("PORT", 5050)))
