# Guía rápida en español

Instala desde el repositorio publicado:

```bash
curl -fsSL https://raw.githubusercontent.com/raimondarias/pterodactyl-installer/main/install.sh -o ptero-setup.sh && sudo bash ptero-setup.sh
```

La primera pregunta estará en inglés: **Which language would you like to use?**. Después se descarga únicamente el paquete del idioma elegido, se verifica y comienza el asistente sin repetir esa pregunta. Esta ruta requiere haber subido el proyecto completo a `main`; consulta [cómo publicarlo](UPLOAD.md).

Al comenzar verás **1. English · 2. Español · 3. Português (Brasil)**. Selecciona 2 para usar todo el asistente en español. El idioma también se puede cambiar desde el menú.

Selecciona **Simple (Recomendado)** o **Avanzado**, y después:

- **Standalone nativo (recomendado), primero**, o Docker.
- MariaDB (recomendado) o MySQL.
- IP pública IPv4 de la máquina, con HTTP y sin SSL; o dominio/subdominio, con HTTPS recomendado.
- Correo, nombre de usuario y contraseña oculta del primer administrador. Si dejas la contraseña vacía se genera una y se muestra para que la guardes.
- SMTP opcional, configurable más tarde.

El modo avanzado también permite elegir versión, PHP 8.3/8.4 en standalone, puerto HTTP, IP de escucha y zona horaria. Las decisiones se muestran antes de instalar.

El motor se elige una sola vez para Panel y juegos. El asistente también ofrece preparar un host SQL local aislado en Docker, registrar uno existente o dejarlo para después (por defecto). La opción local usa Docker incluso con Panel standalone y sirve para los juegos de esta máquina. El host se registra automáticamente en el Panel y entrega host, puerto, usuario y contraseña en pantalla y en un archivo privado. Avanzado permite personalizar las credenciales y asociar un nodo existente; 0 lo deja global. Cada servidor de juego necesita un límite de bases de datos mayor que cero.

Los menús 20–22 configuran el host, muestran sus credenciales y crean una copia de las bases locales. El idioma cambia en la opción 23. Las bases de juegos y sus credenciales se conservan al purgar el Panel; sus datos SQL requieren su propia copia. El host remoto debe estar preparado y accesible; su instalación y sus copias no se hacen a distancia. La restauración de la copia física SQL sigue siendo manual con la imagen original. Consulta los detalles de redes, firewall y restauración en [la guía principal](../README.md#game-database-hosts).

Vista previa sin root ni instalación:

```bash
bash scripts/run_local.sh --language es --preview
```

Se aceptan Ubuntu 22.04/24.04/26.04 y Debian 12/13 con systemd. Se necesitan root, Python 3.10+, al menos 4 GiB libres y memoria suficiente. El arranque instala Python si falta. No se necesitan paquetes de pip. MySQL nativo en Debian requiere amd64; en Debian ARM64 usa MariaDB o Docker.

Wings necesita Docker para ejecutar juegos, aunque el Panel sea standalone. Puedes usar Wings como servicio systemd (recomendado) o como contenedor oficial. Crea primero ubicación, nodo y allocations en el Panel, y vincúlalo con el token Auto-Deploy. El token se introduce oculto y no pasa por argumentos de proceso.

El menú permite instalar/desinstalar ambos componentes juntos o separados, actualizar, emitir SSL para Wings, hacer copias, restaurar, consultar diagnósticos/registros y configurar correo/administradores.

Al desinstalar se conservan los datos por defecto. Borrarlos requiere confirmación y una copia correcta. Las copias del Panel incluyen SQL y las claves originales; **no incluyen los archivos ni mundos de los juegos**. Guarda los archivos `.tar.gz` y `.sha256` fuera del servidor.

Panel v2 es beta. Los tests automatizados y las comprobaciones reales de archivos/configuraciones no sustituyen probar un despliegue completo en un VPS limpio. Consulta [el informe](../test-results/REPORT.md), [la guía principal](../README.md) y [las pruebas de integración](TESTING.md).

La interfaz abre una TUI de pantalla completa en una terminal SSH compatible. Usa ↑/↓ para moverte, Tab o ←/→ para cambiar de grupo, Enter para elegir, / para buscar, F5 para actualizar estados y Esc/Q para volver o salir. Las acciones sin requisitos cumplidos explican qué falta y no se ejecutan. En una máquina nueva, Diagnóstico muestra información útil y el siguiente paso. Prueba sin instalar con `bash ptero-setup.sh --preview`; usa `--plain` para menú numérico y `--no-animation` para reducir movimiento. [Detalles y capturas](TUI.md).
