from repmgr.application import app, db

if __name__ == "__main__":
    db.create_all()
    app.run()
#from repmgr.application import app, db; db.create_all(); app.run(debug=False)