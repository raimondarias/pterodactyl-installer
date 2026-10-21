"""Use Pterodactyl's own user creation contract; credentials travel via stdin."""
import json
import tempfile


def create(installer, state, prefix, app_path):
    data = {**state["admin"], "password": installer.admin_password}
    installer.run.secrets.add(data["password"])
    code = (f"require {json.dumps(str(app_path) + '/vendor/autoload.php')};"
            f"$app=require {json.dumps(str(app_path) + '/bootstrap/app.php')};"
            "$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();"
            "$data=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);"
            "$app->make(Pterodactyl\\Contracts\\Users\\CreatesUsers::class)->create($data);"
            "fwrite(STDOUT,\"Administrator created.\\n\");")
    with tempfile.TemporaryFile() as stream:
        stream.write(json.dumps(data).encode())
        stream.seek(0)
        installer.run.run([*prefix, "-r", code], input_file=stream, label="Creating the first administrator")
