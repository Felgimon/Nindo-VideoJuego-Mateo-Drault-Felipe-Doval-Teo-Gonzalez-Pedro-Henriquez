using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Slots de material de un personaje que el código enciende o tiñe sin duplicar materiales:
    ///  - 'Glint': el filo de la katana, los zunchos del martillo de Gorō. El combate lo prende durante el
    ///    aviso del golpe (SetGlint: dorado = se puede desviar, rojo = imparable) para que el arma, que es lo
    ///    que el jugador mira, diga cuándo apretar parry.
    ///  - cualquier slot por nombre (CoverSlot / Pulse): la bandana de Kaito, tapada con el material del pelo
    ///    hasta que la recibe y con un destello al atársele sola (CharacterFactory.SetBandana).
    /// Los destellos usan un MaterialPropertyBlock por (renderer, índice de material): el resto de los materiales
    /// sigue en el SRP Batcher y, con todo apagado, el bloque se limpia. Tapar un slot cambia el material en
    /// sharedMaterials (no un bloque): así HitFlash guarda y devuelve el material tapado y el cuerpo no sale del
    /// batching durante todo el prólogo. El Update se apaga solo cuando no hay un destello en curso.
    /// CharacterFactory.BuildModel lo agrega y registra los slots al convertir los materiales a Nindo/CharacterLit.
    /// </summary>
    public class CharacterGlint : MonoBehaviour
    {
        public const string GlintSlot = "Glint";
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        class Slot
        {
            public Renderer r;
            public int index;
            public string name;
            public Color baseEmission;       // la del material (ojos de Gorō): el destello se suma encima
            public Material own;             // el material propio mientras el slot está tapado con otro
            public Color glow;               // emisión fija pedida por código
            public Color pulse; public float pulseStart, pulseLen;
        }

        readonly List<Slot> slots = new List<Slot>();
        MaterialPropertyBlock mpb;

        public bool HasGlint
        {
            get { foreach (var s in slots) if (s.name == GlintSlot) return true; return false; }
        }

        /// <summary>Lo llama CharacterFactory por cada material convertido (nombre base, sin sufijos).</summary>
        public void Register(Renderer r, int index, string slotName, Material material)
        {
            slots.Add(new Slot
            {
                r = r, index = index, name = slotName,
                baseEmission = material != null && material.HasProperty(EmissionId) ? material.GetColor(EmissionId) : Color.black,
            });
        }

        /// <summary>Enciende el filo de las armas: color HDR * intensidad (0 apaga y devuelve el batching).</summary>
        public void SetGlint(Color color, float intensity)
        {
            Color c = color * Mathf.Max(0f, intensity); c.a = 1f;
            foreach (var s in slots)
                if (s.name == GlintSlot) { s.glow = c; Apply(s); }
        }

        /// <summary>Tapa un slot con el material que tiene ahora otro slot del mismo renderer (la bandana con
        /// el pelo, ya levantado por LiftBlacks); withSlot null le devuelve su material propio.</summary>
        public void CoverSlot(string slotName, string withSlot)
        {
            foreach (var s in slots)
            {
                if (s.name != slotName || s.r == null) continue;
                var mats = s.r.sharedMaterials;
                if (s.index >= mats.Length) continue;
                Material m = s.own;
                if (withSlot != null)
                {
                    var w = slots.Find(o => o.name == withSlot && o.r == s.r && o.index < mats.Length);
                    if (w == null) continue;
                    if (s.own == null) s.own = mats[s.index];
                    m = mats[w.index];
                }
                else s.own = null;
                if (m == null || mats[s.index] == m) continue;
                mats[s.index] = m;
                s.r.sharedMaterials = mats;
                Apply(s);
            }
        }

        /// <summary>Destello que arranca en 'color' y se apaga solo en 'seconds' (tiempo real: va en cinemáticas lentas).</summary>
        public void Pulse(string slotName, Color color, float seconds)
        {
            bool any = false;
            foreach (var s in slots)
                if (s.name == slotName) { s.pulse = color; s.pulseStart = Time.unscaledTime; s.pulseLen = Mathf.Max(0.01f, seconds); any = true; }
            if (any) enabled = true;
        }

        void Update()
        {
            bool busy = false;
            foreach (var s in slots)
            {
                if (s.pulseLen <= 0f) continue;
                if (Time.unscaledTime - s.pulseStart >= s.pulseLen) s.pulseLen = 0f;
                else busy = true;
                Apply(s);
            }
            if (!busy) enabled = false;
        }

        void Apply(Slot s)
        {
            if (s.r == null) return;
            Color pulse = Color.black;
            if (s.pulseLen > 0f)
            {
                // sube de golpe y se apaga con curva suave (el "flash" de la bandana)
                float k = 1f - Mathf.Clamp01((Time.unscaledTime - s.pulseStart) / s.pulseLen);
                pulse = s.pulse * (k * k);
            }
            bool emissive = s.glow.maxColorComponent > 0.001f || pulse.maxColorComponent > 0.001f;
            if (!emissive)
            {
                s.r.SetPropertyBlock(null, s.index);
                return;
            }
            mpb ??= new MaterialPropertyBlock();
            mpb.Clear();
            // tapado, el slot se hace pasar por otro material (la bandana de pelo): sin su emisión propia
            Color e = (s.own != null ? Color.black : s.baseEmission) + s.glow + pulse; e.a = 1f;
            mpb.SetColor(EmissionId, e);
            s.r.SetPropertyBlock(mpb, s.index);
        }
    }
}
