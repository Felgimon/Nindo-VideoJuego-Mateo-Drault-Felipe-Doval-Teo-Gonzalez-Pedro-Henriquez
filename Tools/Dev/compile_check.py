"""
Compila el C# del juego SIN abrir Unity (chequeo rápido de errores de compilación).

Toma el Assembly-CSharp.csproj que genera Unity en el proyecto principal (el que tiene la carpeta
Library con las DLLs de Unity y los paquetes), le cambia las rutas relativas por absolutas y
compila los .cs de la copia de trabajo que se indique (por defecto, la de este repo) con
`dotnet msbuild`. Sirve en worktrees y en copias sin Library.

Uso:
  python Tools/Dev/compile_check.py [--project RUTA_AL_PROYECTO_UNITY_CON_LIBRARY] [--src RUTA_Assets]

Sale con código 0 si compila; imprime los errores (sin repetir) si no.
Requisitos: dotnet SDK en el PATH y haber abierto el proyecto en Unity al menos una vez (Library/).
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None, help="proyecto Unity con Library/ y Assembly-CSharp.csproj")
    ap.add_argument("--src", default=os.path.join(REPO, "Nindo", "Assets"), help="carpeta Assets cuyos .cs se compilan")
    a = ap.parse_args()

    project = a.project
    if project is None:
        # por defecto: el checkout principal (los worktrees viven en <principal>/.claude/worktrees/<x>)
        cand = [os.path.join(REPO, "Nindo")]
        m = re.search(r"^(.*)[\\/]\.claude[\\/]worktrees[\\/][^\\/]+$", REPO)
        if m:
            cand.insert(0, os.path.join(m.group(1), "Nindo"))
        project = next((c for c in cand if os.path.exists(os.path.join(c, "Assembly-CSharp.csproj"))), None)
    if project is None or not os.path.exists(os.path.join(project, "Assembly-CSharp.csproj")):
        sys.exit("No encuentro Assembly-CSharp.csproj: abrí el proyecto en Unity una vez o pasá --project")

    text = open(os.path.join(project, "Assembly-CSharp.csproj"), encoding="utf-8-sig").read()
    # referencias: rutas relativas al proyecto -> absolutas
    def absref(m):
        p = m.group(2)
        if not os.path.isabs(p):
            p = os.path.normpath(os.path.join(project, p))
        return m.group(1) + p + m.group(3)
    text = re.sub(r'(<HintPath>)([^<]+)(</HintPath>)', absref, text)
    text = re.sub(r'(<ProjectReference Include=")([^"]+)(")', absref, text)
    # fuentes: todos los .cs de --src fuera de carpetas Editor (Assembly-CSharp-Editor aparte)
    text = re.sub(r'\s*<Compile Include="[^"]+" />', "", text)
    src = os.path.abspath(a.src)
    files = [f for f in glob.glob(os.path.join(src, "**", "*.cs"), recursive=True)
             if os.sep + "Editor" + os.sep not in f and "PackageCache" not in f]
    items = "".join('\n    <Compile Include="%s" />' % f for f in files)
    text = text.replace("<ItemGroup>", "<ItemGroup>" + items, 1)
    # analizadores/generadores con ruta relativa
    text = re.sub(r'(<Analyzer Include=")([^"]+)(")', absref, text)

    tmp = tempfile.mkdtemp(prefix="nindo_cc_")
    proj = os.path.join(tmp, "Check.csproj")
    open(proj, "w", encoding="utf-8").write(text)
    r = subprocess.run(["dotnet", "msbuild", proj, "-t:Build", "-nologo", "-v:q",
                        "-p:OutputPath=" + os.path.join(tmp, "out") + os.sep,
                        "-p:BaseIntermediateOutputPath=" + os.path.join(tmp, "obj") + os.sep],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    errs = sorted({re.sub(r"\s*\[[^\]]*\]\s*$", "", l.strip()) for l in (r.stdout + r.stderr).splitlines() if " error " in l})
    print("%d archivos .cs" % len(files))
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    print("compila OK")


if __name__ == "__main__":
    main()
