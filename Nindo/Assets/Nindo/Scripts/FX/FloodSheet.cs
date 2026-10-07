using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Capa de agua sobre la plataforma de la arena del lago (shader Nindo/Foam Water, modo 1). Dos usos:
    ///  * película mojada (SetWet): el rocío de la cascada moja la madera; brilla un poco y la llovizna deja
    ///    anillitos. Es el estado normal de la fase 1.
    ///  * crecida (Rise / Drain): en la fase 2 el agua sube ~12 cm, con espuma contra las barandas, y cada paso de
    ///    Kaito y cada golpe que pida Ripple() abre un anillo. Covers() dice si un punto está bajo el agua (para
    ///    cambiar los pasos por 'step_water').
    /// Plataforma: lake_arena_platform, octógono con los lados mirando a los puntos cardinales (yaw 225 = múltiplo
    /// de 45°, así que el octógono queda igual en el mundo).
    /// </summary>
    public class FloodSheet : MonoBehaviour
    {
        public const float MaxDepth = 0.12f;

        public float Level01 => level;
        public bool IsFlooded => level > 0.5f;

        float level, levelFrom, levelTo, levelT, levelDur;
        float wet, wetFrom, wetTo, wetT, wetDur;
        float deckY, inradius;
        Vector3 center;
        Material mat;
        Mesh mesh;
        MeshRenderer mr;
        readonly Vector4[] ripples = new Vector4[6];
        int nextRipple;
        float stepTimer;

        static readonly int IdLevel = Shader.PropertyToID("_Level"), IdWet = Shader.PropertyToID("_Wet"), IdSpray = Shader.PropertyToID("_Spray");
        static readonly int[] IdRipple =
        {
            Shader.PropertyToID("_Ripple0"), Shader.PropertyToID("_Ripple1"), Shader.PropertyToID("_Ripple2"),
            Shader.PropertyToID("_Ripple3"), Shader.PropertyToID("_Ripple4"), Shader.PropertyToID("_Ripple5"),
        };

        /// <summary>deckCenter = centro de la plataforma a la altura del piso; circumRadius = radio a los vértices.</summary>
        public static FloodSheet Create(Transform parent, Vector3 deckCenter, float circumRadius)
        {
            var go = new GameObject("FloodSheet");
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(deckCenter, Quaternion.identity);
            var f = go.AddComponent<FloodSheet>();
            f.Build(deckCenter, circumRadius);
            return f;
        }

        void Build(Vector3 deckCenter, float circumRadius)
        {
            center = deckCenter;
            deckY = deckCenter.y;
            var sh = Resources.Load<Shader>("Shaders/NindoFoamWater");
            if (sh == null || !sh.isSupported) { enabled = false; return; }
            mat = new Material(sh) { name = "FloodSheet" };
            mat.SetFloat("_Mode", 1f);
            // antes que los avisos (Nindo/Telegraph, Transparent-10): con 12 cm de agua encima, los anillos y las zonas de
            // la fase 2 de Mizuchi quedaban debajo de la crecida, lavados al 42 %
            mat.renderQueue = (int)RenderQueue.Transparent - 11;
            for (int i = 0; i < ripples.Length; i++) ripples[i] = new Vector4(0f, 0f, 0f, -99f);
            // un poco adentro de las barandas (postes al 98.5 % del radio)
            float rc = circumRadius - 0.3f;
            inradius = rc * Mathf.Cos(22.5f * Mathf.Deg2Rad);
            mesh = BuildOctagon(rc);
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            mr = gameObject.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            Apply();
        }

        /// <summary>Octógono en anillos concéntricos (vértices + puntos medios de los lados); uv.x = metros hasta el
        /// borde, exacto con interpolación lineal porque cada anillo es un octógono semejante.</summary>
        static Mesh BuildOctagon(float rc)
        {
            float[] rings = { 0f, 0.5f, 0.8f, 0.93f, 1f };
            const int N = 16;
            float ri = rc * Mathf.Cos(22.5f * Mathf.Deg2Rad);
            var v = new Vector3[1 + (rings.Length - 1) * N];
            var uv = new Vector2[v.Length];
            var col = new Color[v.Length];
            v[0] = Vector3.zero; uv[0] = new Vector2(ri, 0f); col[0] = Color.white;
            for (int r = 1; r < rings.Length; r++)
                for (int k = 0; k < N; k++)
                {
                    float a = (22.5f * k) * Mathf.Deg2Rad + 22.5f * Mathf.Deg2Rad;
                    // los pares son vértices del octógono; los impares, puntos medios de los lados
                    float rad = (k % 2 == 0 ? rc : ri) * rings[r];
                    int i = 1 + (r - 1) * N + k;
                    v[i] = new Vector3(Mathf.Cos(a) * rad, 0f, Mathf.Sin(a) * rad);
                    uv[i] = new Vector2((1f - rings[r]) * ri, a * rad);
                    col[i] = Color.white;
                }
            var tri = new System.Collections.Generic.List<int>();
            for (int k = 0; k < N; k++) { tri.Add(0); tri.Add(1 + (k + 1) % N); tri.Add(1 + k); }
            for (int r = 1; r < rings.Length - 1; r++)
                for (int k = 0; k < N; k++)
                {
                    int a = 1 + (r - 1) * N + k, b = 1 + (r - 1) * N + (k + 1) % N;
                    int c = a + N, d = b + N;
                    tri.Add(a); tri.Add(b); tri.Add(c);
                    tri.Add(b); tri.Add(d); tri.Add(c);
                }
            var m = new Mesh { name = "FloodSheet", vertices = v, uv = uv, colors = col, triangles = tri.ToArray() };
            m.RecalculateBounds();
            return m;
        }

        // ------------------------------------------------------------------ API
        /// <summary>Sube la crecida en 'seconds'.</summary>
        public void Rise(float seconds)
        {
            levelFrom = level; levelTo = 1f; levelT = 0f; levelDur = Mathf.Max(0.01f, seconds);
        }

        /// <summary>Baja el agua en 'seconds' (0 = al instante, para los reintentos).</summary>
        public void Drain(float seconds = 2f)
        {
            if (seconds <= 0f) { level = levelTo = 0f; levelDur = 0f; Apply(); return; }
            levelFrom = level; levelTo = 0f; levelT = 0f; levelDur = seconds;
        }

        /// <summary>Película mojada (0 seca .. 1 empapada).</summary>
        public void SetWet(float wet01, float seconds = 1.5f)
        {
            if (seconds <= 0f) { wet = wetTo = Mathf.Clamp01(wet01); wetDur = 0f; Apply(); return; }
            wetFrom = wet; wetTo = Mathf.Clamp01(wet01); wetT = 0f; wetDur = seconds;
        }

        /// <summary>De dónde viene la llovizna: la película mojada y sus anillitos se apagan a 'radius' metros de ahí
        /// (la baranda del lado de la cascada brilla mojada; la de la entrada queda seca).</summary>
        public void SetSpraySource(Vector3 worldPos, float radius)
        {
            if (mat != null) mat.SetVector(IdSpray, new Vector4(worldPos.x, worldPos.y, worldPos.z, Mathf.Max(1f, radius)));
        }

        /// <summary>Anillo que se abre en el agua (pasos, pilares, el cuerpo del koi al caer). Hasta 6 a la vez.</summary>
        public void Ripple(Vector3 worldPos)
        {
            if (mat == null) return;
            ripples[nextRipple] = new Vector4(worldPos.x, worldPos.y, worldPos.z, Time.time);
            mat.SetVector(IdRipple[nextRipple], ripples[nextRipple]);
            nextRipple = (nextRipple + 1) % ripples.Length;
        }

        /// <summary>¿Ese punto está bajo la crecida? (dentro del octógono y con agua de verdad, no la película).</summary>
        public bool Covers(Vector3 worldPos)
        {
            if (level < 0.3f) return false;
            Vector3 d = worldPos - center;
            if (Mathf.Abs(d.y) > 1.2f) return false;
            // distancia "octogonal": el máximo de las proyecciones sobre las normales de los 8 lados
            float m = Mathf.Max(Mathf.Max(Mathf.Abs(d.x), Mathf.Abs(d.z)), (Mathf.Abs(d.x) + Mathf.Abs(d.z)) * 0.70710678f);
            return m <= inradius;
        }

        // ------------------------------------------------------------------ frame
        void Update()
        {
            float dt = Time.deltaTime;
            bool changed = false;
            if (levelDur > 0f)
            {
                levelT += dt;
                float k = Mathf.Clamp01(levelT / levelDur);
                level = Mathf.Lerp(levelFrom, levelTo, k * k * (3f - 2f * k));
                if (k >= 1f) levelDur = 0f;
                changed = true;
            }
            if (wetDur > 0f)
            {
                wetT += dt;
                float k = Mathf.Clamp01(wetT / wetDur);
                wet = Mathf.Lerp(wetFrom, wetTo, k);
                if (k >= 1f) wetDur = 0f;
                changed = true;
            }
            if (changed) Apply();
            // los pasos de Kaito abren anillos mientras hay agua
            var p = Game.Player;
            if (level > 0.3f && p != null && Covers(p.transform.position))
            {
                stepTimer -= dt;
                float speed = p.Velocity.magnitude;
                if (speed > 1f && stepTimer <= 0f)
                {
                    stepTimer = Mathf.Lerp(0.42f, 0.24f, Mathf.InverseLerp(1f, 8f, speed));
                    Ripple(p.transform.position);
                    // con la crecida (no la película mojada) cada paso chapotea encima del paso de madera
                    if (IsFlooded) Game.Audio?.Play("step_water", p.transform.position, 0.45f, 0.12f);
                }
            }
        }

        void Apply()
        {
            if (mat == null) return;
            transform.position = new Vector3(center.x, deckY + 0.015f + level * MaxDepth, center.z);
            mat.SetFloat(IdLevel, level);
            mat.SetFloat(IdWet, wet);
            if (mr != null) mr.enabled = level > 0.001f || wet > 0.001f;
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (mesh != null) Destroy(mesh);
        }
    }
}
