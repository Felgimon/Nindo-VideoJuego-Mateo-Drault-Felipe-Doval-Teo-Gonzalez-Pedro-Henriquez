"""Genera Scripts/Enemies/Bosses/KokuyoTimings.cs desde Art/Characters/Kokuyo/Kokuyo.fbx.json.

El JSON lo escribe Tools/Blender/bosses/kokuyo/build_kokuyo.py junto con el FBX: es la única fuente de los
tiempos de cada clip (apex, contacto, ventana activa, ritmo de la suelta, alcance de la hoja, avance del
transform por cuadro y eventos). Así los AttackDef de Kokuyō (KokuyoMoves.cs) no pueden despegarse de lo que
se ve: si se rehace un clip, se corre este script y se recompila.

Uso: python Tools/Unity/kokuyo_timings.py
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unity_yaml as U

SRC = os.path.join(U.ASSETS, "Nindo", "Art", "Characters", "Kokuyo", "Kokuyo.fbx.json")
DST = os.path.join(U.ASSETS, "Nindo", "Scripts", "Enemies", "Bosses", "KokuyoTimings.cs")


def f(x):
    s = ("%.4f" % float(x)).rstrip("0")
    if s.endswith("."):
        s += "0"
    return s + "f"


def arr(xs):
    return "null" if not xs else "new[] { " + ", ".join(f(x) for x in xs) + " }"


def ident(name):
    return name[0].upper() + name[1:]


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    clips = data["clips"]
    out = []
    w = out.append
    w("// Generado por Tools/Unity/kokuyo_timings.py desde Kokuyo.fbx.json: no editar a mano.")
    w("namespace Nindo")
    w("{")
    w("    /// <summary>Tiempos de un clip de Kokuyō tal como los mide el build de Blender (normalizados 0..1).</summary>")
    w("    public sealed class KokuyoClip")
    w("    {")
    w("        public readonly string State;")
    w("        public readonly int Frames;")
    w("        public readonly float Seconds, Apex, Contact, ActiveEnd, ReleaseRate, Reach;")
    w("        /// <summary>Metros que avanzó el transform en cada cuadro del clip (null = no se mueve).</summary>")
    w("        public readonly float[] Travel;")
    w("        /// <summary>Pose con la que empieza y con la que termina (READY, LOW_L, GUARD...): encadenar dos clips")
    w("        /// cuyas poses no coinciden pide un fundido más largo.</summary>")
    w("        public readonly string ChainFrom, ChainTo;")
    w("        readonly string[] eventNames;")
    w("        readonly float[] eventTimes;")
    w("")
    w("        public KokuyoClip(string state, int frames, float seconds, float apex, float contact, float activeEnd, float releaseRate,")
    w("            float reach, float[] travel, string chainFrom, string chainTo, string[] eventNames, float[] eventTimes)")
    w("        {")
    w("            State = state; Frames = frames; Seconds = seconds; Apex = apex; Contact = contact; ActiveEnd = activeEnd;")
    w("            ReleaseRate = releaseRate; Reach = reach; Travel = travel; ChainFrom = chainFrom; ChainTo = chainTo;")
    w("            this.eventNames = eventNames; this.eventTimes = eventTimes;")
    w("        }")
    w("")
    w("        /// <summary>Tiempo normalizado del primer evento con ese nombre (-1 si el clip no lo tiene).</summary>")
    w("        public float Event(string name)")
    w("        {")
    w("            for (int i = 0; i < eventNames.Length; i++) if (eventNames[i] == name) return eventTimes[i];")
    w("            return -1f;")
    w("        }")
    w("")
    w("        /// <summary>Normalizado de un cuadro del clip.</summary>")
    w("        public float FrameNorm(float frame) => Frames > 0 ? frame / Frames : 0f;")
    w("")
    w("        /// <summary>Metros avanzados en el tiempo normalizado 'n' (interpolado entre cuadros).</summary>")
    w("        public float TravelAt(float n)")
    w("        {")
    w("            if (Travel == null) return 0f;")
    w("            float x = UnityEngine.Mathf.Clamp(n, 0f, 1f) * Frames;")
    w("            int i = UnityEngine.Mathf.Min((int)x, Travel.Length - 1);")
    w("            int j = UnityEngine.Mathf.Min(i + 1, Travel.Length - 1);")
    w("            return Travel[i] + (Travel[j] - Travel[i]) * (x - i);")
    w("        }")
    w("    }")
    w("")
    w("    public static class KokuyoTimings")
    w("    {")
    w("        public const float BindHeight = %s;" % f(data["bind_height"]))
    for name, c in clips.items():
        nm = c.get("normalized", {})
        t = c.get("timing", {})
        act = nm.get("active")
        contact = nm.get("contact", act[0] if act else 0.0)
        active_end = act[1] if act else contact
        apex = nm.get("apex", 0.0)
        rr = c.get("release_rate") or t.get("release_rate") or 1.6
        evs = c.get("events", [])
        names = "new string[] { " + ", ".join('"%s"' % e["fn"] for e in evs) + " }" if evs else "new string[0]"
        times = "new[] { " + ", ".join(f(e["t"]) for e in evs) + " }" if evs else "new float[0]"
        w("        public static readonly KokuyoClip %s = new KokuyoClip(\"%s\", %d, %s, %s, %s, %s, %s, %s," % (
            ident(name), name, c["frames"], f(c["seconds"]), f(apex), f(contact), f(active_end), f(rr), f(c.get("reach_m") or 0.0)))
        w("            %s," % arr(c.get("travel_m")))
        w("            \"%s\", \"%s\", %s, %s);" % (t.get("chain_from", ""), t.get("chain_to", ""), names, times))
    # lo que no es un evento pero el juego necesita: hoja clavada de KabutoWari, núcleo seguro del barrido,
    # retroceso del parry
    kw = clips["KabutoWari"]["timing"]
    w("        /// <summary>KabutoWari: la hoja queda clavada entre estos normalizados (castigo libre).</summary>")
    w("        public static readonly float KabutoStuckStart = %s, KabutoStuckEnd = %s;" % (
        f(kw["stuck"][0] / clips["KabutoWari"]["frames"]), f(kw["stuck"][1] / clips["KabutoWari"]["frames"])))
    w("        /// <summary>Ichimonji: radio bajo la empuñadura que la hoja no toca (m).</summary>")
    w("        public const float IchimonjiSafeCore = %s;" % f(clips["Ichimonji"]["timing"]["safe_core_m"]))
    w("        /// <summary>Parried: metros que retrocede con la curva 1 - e^(-10 t) (los pies no patinan con eso).</summary>")
    w("        public const float ParriedKnock = %s;" % f(clips["Parried"]["timing"]["knock_m"]))
    w("    }")
    w("}")
    U.write(DST, "\n".join(out) + "\n")
    U.write_meta(DST, U.MONO_META)
    U.ensure_folder_metas(os.path.dirname(DST))
    print("escrito", os.path.relpath(DST, U.REPO))


if __name__ == "__main__":
    main()
