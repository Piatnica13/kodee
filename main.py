from __init__ import create_app

# Schema/admin/webhook initialization remains an explicit CLI operation.
app = create_app()

if __name__ == '__main__':
    import os
    app.run(port=int(os.getenv('PORT', 5000)), host='127.0.0.1')
