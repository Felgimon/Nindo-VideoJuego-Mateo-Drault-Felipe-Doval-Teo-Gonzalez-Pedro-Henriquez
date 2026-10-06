using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Media luna de pincel delante de Kaito mientras dura la ventana de parry (misma tinta que el aviso ensō,
    /// shader Nindo/Telegraph). El clip ParryStance casi no cambia la silueta y desde la cámara alta no se sabía
    /// si el parry estaba activo ni cuándo se terminaba. Acá:
    ///  * dorada mientras la ventana es PERFECTA, blanco acero después;
    ///  * se achica hacia el centro al ritmo de la ventana: desaparece justo cuando se cierra;
    ///  * si desvía, destella y se apaga; si no llegó nada, se rompe en gris (con el "fiu" del parry al aire).
    /// Un solo quad, un MaterialPropertyBlock por frame.
    /// </summary>
    public class ParryCrescent : MonoBehaviour
    {
        enum End { None, Success, Whiff, Cancel }

        [Tooltip("Arco de la media luna (grados)")] public float arc = 150f;
        public float radius = 0.9f;
        [Tooltip("Altura sobre los pies de Kaito (m): a la altura del pecho, no se mezcla con los anillos del suelo")] public float height = 0.9f;

        static readonly Color Steel = new Color(0.82f, 0.9f, 1f);
        static readonly Color Broken = new Color(0.5f, 0.5f, 0.54f);

        Transform quadT;
        MeshRenderer mr;
        Material mat;
        Mesh quad;
        MaterialPropertyBlock mpb;
        Transform owner;
        float window, perfect, t, outT, seed, span;
        End end;
        bool active;

        static readonly int IdColor = Shader.PropertyToID("_Color"), IdHotColor = Shader.PropertyToID("_HotColor"), IdInk = Shader.PropertyToID("_Ink"),
            IdMode = Shader.PropertyToID("_Mode"), IdProgress = Shader.PropertyToID("_Progress"), IdHot = Shader.PropertyToID("_Hot"),
            IdFlash = Shader.PropertyToID("_Flash"), IdDanger = Shader.PropertyToID("_Danger"), IdAlpha = Shader.PropertyToID("_Alpha"),
            IdRadius = Shader.PropertyToID("_Radius"), IdWidth = Shader.PropertyToID("_Width"), IdDot = Shader.PropertyToID("_Dot"),
            IdMinPx = Shader.PropertyToID("_MinPx"), IdOutcome = Shader.PropertyToID("_Outcome"), IdOutT = Shader.PropertyToID("_OutT"),
            IdSeed = Shader.PropertyToID("_Seed");

        void Awake()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoTelegraph");
            if (sh == null || !sh.isSupported) { enabled = false; return; }
            mat = new Material(sh) { name = "ParryCrescent" };
            mpb = new MaterialPropertyBlock();
            quad = new Mesh { name = "CrescentQuad" };
            quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            quad.RecalculateBounds();
            var go = new GameObject("ParryCrescent");
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = quad;
            mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.enabled = false;
            quadT = go.transform;
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (quad != null) Destroy(quad);
        }

        // ------------------------------------------------------------------ API (la llama Kaito)
        /// <summary>Arranca la ventana: 'window' segundos de juego, los primeros 'perfectWindow' son perfectos.</summary>
        public void Begin(Transform kaito, float window, float perfectWindow)
        {
            if (!enabled) return;
            owner = kaito;
            this.window = Mathf.Max(0.02f, window);
            perfect = Mathf.Clamp(perfectWindow, 0f, this.window);
            t = 0f; outT = 0f; span = arc;
            seed = Random.value * 10f;
            end = End.None;
            active = true;
        }

        /// <summary>Desvió un golpe: destello y se apaga.</summary>
        public void Success() => Finish(End.Success);
        /// <summary>Se cerró la ventana sin nada que desviar: se rompe en gris.</summary>
        public void Whiff() => Finish(End.Whiff);
        /// <summary>Kaito salió del parry por otra cosa (golpe, dash, cinemática): se deshace.</summary>
        public void Cancel() => Finish(End.Cancel);

        void Finish(End e)
        {
            if (!active || end != End.None) return;
            end = e;
            outT = 0f;
        }

        // ------------------------------------------------------------------ por frame
        void LateUpdate()
        {
            if (!active) return;
            if (owner == null) { Hide(); return; }
            // tiempo de juego: igual que la ventana de parry de Kaito (cámara lenta y hit-stop incluidos)
            float dt = Time.deltaTime;
            if (end == End.None) t += dt;
            else
            {
                outT += dt / (end == End.Whiff ? 0.22f : end == End.Success ? 0.14f : 0.1f);
                if (outT >= 1f) { Hide(); return; }
            }

            // lo que queda de ventana: la media luna se achica hacia el centro (al terminar queda del último tamaño)
            if (end == End.None) span = arc * Mathf.Lerp(0.45f, 1f, Mathf.Clamp01(1f - t / window));
            float half = radius * 1.7f + 0.3f;
            Vector3 fwd = owner.forward; fwd.y = 0f;
            if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.forward;
            // el trazo arranca del lado izquierdo y gira en sentido horario: centrado en el frente de Kaito
            Quaternion rot = Quaternion.LookRotation(fwd.normalized, Vector3.up) * Quaternion.Euler(0f, -span * 0.5f, 0f);
            quadT.SetPositionAndRotation(owner.position + Vector3.up * height, rot);
            quadT.localScale = new Vector3(half * 2f, 1f, half * 2f);
            mr.enabled = true;

            bool inPerfect = t <= perfect;
            float hot = end == End.None ? (inPerfect ? 0f : Mathf.Clamp01((t - perfect) / 0.03f)) : 1f;
            Color col = end == End.Whiff ? Broken : TellStyle.Gold;
            Color hotCol = end == End.Whiff ? Broken : end == End.Success ? TellStyle.GoldHot : Steel;
            float flash = end == End.Success ? Mathf.Clamp01(1f - outT * 2f) : 0f;

            mpb.Clear();
            mpb.SetColor(IdColor, col);
            mpb.SetColor(IdHotColor, hotCol);
            mpb.SetColor(IdInk, TellStyle.Ink);
            mpb.SetFloat(IdMode, 0f);
            mpb.SetFloat(IdProgress, span / 360f);
            mpb.SetFloat(IdHot, hot);
            mpb.SetFloat(IdFlash, flash);
            mpb.SetFloat(IdDanger, 0f);
            mpb.SetFloat(IdAlpha, end == End.Whiff ? 0.8f : 1f);
            mpb.SetFloat(IdRadius, radius / half);
            mpb.SetFloat(IdWidth, 0.05f / half);
            mpb.SetFloat(IdDot, 0.08f / half);
            mpb.SetFloat(IdMinPx, 8f);
            // final: desviado = se apaga brillando, al aire = se parte en pedazos, cortado = la tinta se deshace
            mpb.SetFloat(IdOutcome, end == End.None ? 0f : end == End.Whiff ? 1f : end == End.Cancel ? 2f : 3f);
            mpb.SetFloat(IdOutT, outT);
            mpb.SetFloat(IdSeed, seed);
            mr.SetPropertyBlock(mpb);
        }

        void Hide()
        {
            active = false;
            owner = null;
            if (mr != null) mr.enabled = false;
        }
    }
}
