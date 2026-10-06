using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Lo que Kokuyō muestra con su cuerpo (no con la animación): el filo de la nodachi, las cinco grietas del pecho
    /// (una por punto de postura), los ojos y la grieta de la máscara, y las piezas que se le van rompiendo a lo largo
    /// de la pelea (media luna izquierda, hombrera derecha). Las piezas rígidas nunca van en los clips (Write Defaults
    /// las devolvería): se prenden y apagan acá, por renderer, y la sombra viva copia lo mismo (PlanarShadow).
    /// Emisiones por MaterialPropertyBlock: el filo, los ojos y la máscara por CharacterGlint (sus slots se llaman como
    /// los materiales del FBX); cada grieta con su propio bloque porque comparten material.
    /// </summary>
    public class KokuyoLook
    {
        public const string EdgeSlot = "Kokuyo_Edge", SeamsSlot = "Kokuyo_Seams", MaskCrackSlot = "Kokuyo_MaskCrack";
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        // el violeta de las costuras (Kokuyo_Seams), el oro del aviso y el rojo de los imparables, en HDR
        public static readonly Color Violet = new Color(0.75f, 0.54f, 1f);
        public static readonly Color GoldHot = new Color(1f, 0.85f, 0.42f);
        public static readonly Color Red = new Color(1f, 0.29f, 0.23f);
        static readonly Color CrackVein = new Color(0.17f, 0.12f, 0.22f);
        static readonly Color CrackLit = new Color(1.1f, 0.8f, 1.5f);

        readonly CharacterGlint glint;
        readonly Renderer crestL, sodeR, sodeBroken;
        readonly Renderer[] cracks = new Renderer[5];
        readonly float[] crackShown = new float[5], crackFlare = new float[5];
        readonly MaterialPropertyBlock mpb = new MaterialPropertyBlock();
        GameObject crestDebris;
        Vector3 debrisVel, debrisSpin;
        float debrisGround;
        bool debrisFalling, eclipse, sodeShattered;
        float edgeTarget, edgeShown, edgeApplied = -1f;
        Color edgeColor = Violet, edgeColorApplied;

        /// <summary>Emisión base de los ojos, grietas y filo (x3 en el eclipse: lo único que brilla en la oscuridad).</summary>
        float Boost => eclipse ? 3f : 1f;
        public bool CrestSnapped => crestDebris != null;
        public bool SodeShattered => sodeShattered;

        public KokuyoLook(Transform model)
        {
            glint = model.GetComponentInChildren<CharacterGlint>();
            foreach (var r in model.GetComponentsInChildren<Renderer>(true))
            {
                if (!(r is MeshRenderer)) continue;
                string n = r.gameObject.name;
                if (n == "Crest_L") crestL = r;
                else if (n == "Sode_R") sodeR = r;
                else if (n == "Sode_R_Broken") sodeBroken = r;
                else if (n.StartsWith("Crack_") && int.TryParse(n.Substring(6), out int k) && k >= 1 && k <= 5) cracks[k - 1] = r;
            }
            ResetAll();
        }

        /// <summary>Como recién llegado: entero, grietas apagadas, filo violeta tenue.</summary>
        public void ResetAll()
        {
            eclipse = false;
            sodeShattered = false;
            if (crestDebris != null) Object.Destroy(crestDebris);
            crestDebris = null;
            debrisFalling = false;
            if (crestL != null) crestL.enabled = true;
            if (sodeR != null) sodeR.enabled = true;
            // la hombrera rota viene del FBX metida adentro de la sana: se ve solo al apagar la sana
            if (sodeBroken != null) sodeBroken.enabled = false;
            for (int i = 0; i < 5; i++) { crackShown[i] = -1f; crackFlare[i] = 0f; }
            edgeColor = Violet; edgeTarget = edgeShown = 0f; edgeApplied = -1f;
            if (glint != null)
            {
                glint.SetGlow(EdgeSlot, Violet, 0f);
                glint.SetGlow(SeamsSlot, Violet, 0f);
                glint.SetGlow(MaskCrackSlot, Violet, 0f);
            }
            ApplyCracks(0f);
        }

        // ------------------------------------------------------------------ filo
        /// <summary>Color y brillo del filo durante el paso: sube en la anticipación, rojo fijo en los imparables.</summary>
        public void SetEdge(Color c, float intensity) { edgeColor = c; edgeTarget = intensity; }

        /// <summary>El "¡ahora!" en el arma: dorado blanco (parry) o un golpe blanco sobre el rojo (dash).</summary>
        public void GoFlash(bool danger)
        {
            if (glint == null) return;
            glint.Pulse(EdgeSlot, (danger ? new Color(1f, 0.9f, 0.85f) : GoldHot) * 6f, 0.14f);
        }

        // ------------------------------------------------------------------ grietas
        /// <summary>Una grieta salta (punto de postura nuevo, habilidad que lo interrumpe): chispas violetas en el pecho.</summary>
        public void FlareCrack(int index, Vector3 at)
        {
            if (index < 0 || index >= 5) return;
            crackFlare[index] = 1f;
            Game.FX?.Clash(at, Vector3.up, false);
        }

        public void FlareAll()
        {
            for (int i = 0; i < 5; i++) crackFlare[i] = 1f;
        }

        // ------------------------------------------------------------------ piezas
        /// <summary>La media luna izquierda se parte y queda en el suelo (la sombra arrancada se la lleva de un tirón).</summary>
        public void SnapCrest(Vector3 awayFrom)
        {
            if (crestL == null || crestDebris != null) return;
            // una copia suelta en el mundo: el original sigue colgado del hueso (HitFlash y la sombra lo conocen) y se apaga
            crestDebris = Object.Instantiate(crestL.gameObject, crestL.transform.position, crestL.transform.rotation);
            crestDebris.name = "MediaLunaRota";
            crestDebris.transform.localScale = crestL.transform.lossyScale;
            foreach (var c in crestDebris.GetComponentsInChildren<Component>())
                if (!(c is Transform) && !(c is MeshFilter) && !(c is MeshRenderer)) Object.Destroy(c);
            crestL.enabled = false;
            Vector3 out_ = (crestL.transform.position - awayFrom).Flat();
            if (out_.sqrMagnitude < 0.01f) out_ = Vector3.left;
            debrisVel = out_.normalized * 3.2f + Vector3.up * 4.5f;
            debrisSpin = new Vector3(Random.Range(-540f, 540f), Random.Range(-720f, 720f), Random.Range(-540f, 540f));
            debrisGround = awayFrom.y + 0.06f;
            debrisFalling = true;
            Game.FX?.Clash(crestL.transform.position, out_.normalized, true);
            Game.Audio?.Play("clang", crestL.transform.position, 1f, 0.05f);
        }

        /// <summary>La hombrera derecha estalla (primera vez de rodillas en el eclipse).</summary>
        public void ShatterSode()
        {
            if (sodeShattered || sodeR == null) return;
            sodeShattered = true;
            Vector3 p = sodeR.transform.position;
            sodeR.enabled = false;
            if (sodeBroken != null) sodeBroken.enabled = true;
            Game.FX?.Clash(p, Vector3.up, true);
            Game.FX?.Embers(p);
            Game.FX?.Dust(p, 1.4f);
            Game.Audio?.Play("clang", p, 1f, 0.05f);
            Game.Camera?.Shake(0.35f);
        }

        /// <summary>El eclipse: ojos, grietas y filo x3 y la grieta violeta de la máscara encendida.</summary>
        public void SetEclipse(bool on)
        {
            eclipse = on;
            if (glint == null) return;
            glint.SetGlow(SeamsSlot, Violet, on ? 2.2f : 0f);
            glint.SetGlow(MaskCrackSlot, Violet, on ? 2.6f : 0f);
        }

        /// <summary>Cae vencido: sin máscara ni furia, los ojos y las grietas se apagan.</summary>
        public void Extinguish()
        {
            eclipse = false;
            edgeTarget = 0f;
            for (int i = 0; i < 5; i++) crackFlare[i] = 0f;
            if (glint == null) return;
            glint.SetGlow(SeamsSlot, Violet, 0f);
            glint.SetGlow(MaskCrackSlot, Violet, 0f);
        }

        // ------------------------------------------------------------------ por frame
        /// <summary>imbalance = puntos de postura (0..5); kneeling = agotado (todas laten).</summary>
        public void Tick(float imbalance, bool kneeling, float dt)
        {
            edgeShown = Mathf.MoveTowards(edgeShown, edgeTarget, dt * 12f);
            float edge = edgeShown * Boost;
            if (glint != null && (Mathf.Abs(edge - edgeApplied) > 0.01f || edgeColor != edgeColorApplied))
            {
                edgeApplied = edge; edgeColorApplied = edgeColor;
                glint.SetGlow(EdgeSlot, edgeColor, edge);
            }
            for (int i = 0; i < 5; i++) crackFlare[i] = Mathf.MoveTowards(crackFlare[i], 0f, dt * 2.5f);
            float breath = kneeling ? 0.75f + 0.25f * Mathf.Sin(Time.time * 7f) : 1f;
            ApplyCracks(imbalance, breath);
            TickDebris(dt);
        }

        void ApplyCracks(float imbalance, float breath = 1f)
        {
            for (int i = 0; i < 5; i++)
            {
                var r = cracks[i];
                if (r == null) continue;
                float lit = Mathf.Clamp01(imbalance - i);
                float k = Mathf.Max(lit * breath, crackFlare[i] * 1.6f) * Boost;
                // un bloque por grieta y solo cuando cambia: las cinco comparten material
                if (Mathf.Abs(k - crackShown[i]) < 0.01f) continue;
                crackShown[i] = k;
                if (k <= 0.001f) { r.SetPropertyBlock(null); continue; }
                mpb.Clear();
                Color e = Color.Lerp(CrackVein, CrackLit * k, Mathf.Clamp01(k)); e.a = 1f;
                if (k > 1f) e = CrackLit * k;
                mpb.SetColor(EmissionId, e);
                r.SetPropertyBlock(mpb);
            }
        }

        void TickDebris(float dt)
        {
            if (!debrisFalling || crestDebris == null) return;
            var t = crestDebris.transform;
            debrisVel += Physics.gravity * dt;
            Vector3 p = t.position + debrisVel * dt;
            t.Rotate(debrisSpin * dt, Space.World);
            if (p.y <= debrisGround)
            {
                // rebota una vez y queda tirada en las losas
                p.y = debrisGround;
                if (debrisVel.y < -3f) { debrisVel = new Vector3(debrisVel.x * 0.35f, -debrisVel.y * 0.25f, debrisVel.z * 0.35f); debrisSpin *= 0.3f; Game.Audio?.Play("clang", p, 0.5f, 0.1f); }
                else debrisFalling = false;
            }
            t.position = p;
        }
    }
}
