using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Las "cuerdas de sombra" con que Kokuyō ata al abuelo al poste (prop binding_post). Tres vueltas que abrazan
    /// el poste y al abuelo (muslos, cintura y pecho) más una cruz sobre el pecho y dos cabos colgando del nudo,
    /// en tubos facetados con Nindo/ShadowRope: violeta oscuro con hebras que brillan y pulsos que corren.
    /// Una luz violeta tenue lo baña (se lee desde la arena: "ahí está el abuelo"). Dissolve las deshace con un
    /// borde encendido y motas que suben cuando Kokuyō cae; Restore las vuelve a atar (reintentos).
    /// Las medidas salen de los bounds del abuelo, así sirven con su modelo actual y con el pulido.
    /// </summary>
    public class ShadowRopes : MonoBehaviour
    {
        static readonly int IdDissolve = Shader.PropertyToID("_Dissolve"), IdSeed = Shader.PropertyToID("_Seed");
        static readonly Color GlowColor = new Color(0.753f, 0.541f, 1f);     // #c08aff (glow_purple)

        public bool Bound { get; private set; }

        MeshRenderer rope;
        Mesh ropeMesh;
        Material mat;
        Light glow;
        ParticleSystem motes;
        readonly List<Vector3> path = new List<Vector3>();   // puntos de las cuerdas (para las motas al deshacerse)
        float dissolve, glowBase = 1.2f;
        Coroutine routine;

        /// <summary>Ata a 'captive' (el NPC del abuelo) contra 'post' (el binding_post). Devuelve null si falta algo.</summary>
        public static ShadowRopes Bind(Transform post, Transform captive, Transform parent)
        {
            if (post == null || captive == null) return null;
            var sh = Resources.Load<Shader>("Shaders/NindoShadowRope");
            if (sh == null || !sh.isSupported)
            {
                Debug.LogWarning("[Nindo] No compila Nindo/ShadowRope: el abuelo queda sin las cuerdas de sombra.");
                return null;
            }
            var go = new GameObject("CuerdasDeSombra");
            go.transform.SetParent(parent, false);
            var r = go.AddComponent<ShadowRopes>();
            r.Build(post, captive, sh);
            return r;
        }

        void Build(Transform post, Transform captive, Shader sh)
        {
            // medidas del abuelo: alto y medio ancho (los renderers apagados, como el ninja del FBX, no cuentan)
            Bounds b = new Bounds(captive.position + Vector3.up * 0.7f, new Vector3(0.5f, 1.4f, 0.4f));
            bool any = false;
            foreach (var r in captive.GetComponentsInChildren<Renderer>())
            {
                if (!r.enabled || !(r is SkinnedMeshRenderer || r is MeshRenderer)) continue;
                if (!any) { b = r.bounds; any = true; } else b.Encapsulate(r.bounds);
            }
            float height = Mathf.Clamp(b.max.y - captive.position.y, 0.9f, 2.2f);
            Vector3 p = post.position, c = captive.position;
            Vector3 axis = (c - p); axis.y = 0f;
            float dist = axis.magnitude;
            axis = dist > 0.01f ? axis / dist : Vector3.back;
            Vector3 side = Vector3.Cross(Vector3.up, axis);
            float halfW = Mathf.Clamp(Mathf.Abs(Vector3.Dot(b.extents, new Vector3(Mathf.Abs(side.x), 0f, Mathf.Abs(side.z)))), 0.18f, 0.4f);
            // las vueltas abrazan poste + abuelo: centro entre los dos, largo hasta la espalda del poste y el pecho del abuelo
            Vector3 mid = (p + c) * 0.5f + axis * 0.04f;
            float along = dist * 0.5f + 0.27f;

            var v = new List<Vector3>(); var uv = new List<Vector2>(); var t = new List<int>();
            var loops = new[] { 0.38f, 0.6f, 0.8f };
            for (int k = 0; k < loops.Length; k++)
            {
                float y = c.y + height * loops[k];
                float across = halfW * (k == 2 ? 1.05f : k == 1 ? 1.12f : 0.95f) + 0.05f;
                var pts = new List<Vector3>();
                const int N = 26;
                for (int i = 0; i < N; i++)
                {
                    float a = i * Mathf.PI * 2f / N;
                    // adelante (sobre el abuelo) la cuerda baja un poco: tensa contra el poste, floja al frente
                    float front = Mathf.Max(0f, Mathf.Cos(a));
                    Vector3 q = mid + axis * Mathf.Cos(a) * along + side * Mathf.Sin(a) * across;
                    q.y = y - 0.05f * front + 0.012f * Mathf.Sin(a * 3f + k);
                    pts.Add(q);
                }
                Tube(v, uv, t, pts, 0.027f, 6, true);
            }
            // cruz sobre el pecho (de la vuelta de arriba a la del medio) y dos cabos colgando del nudo
            Vector3 chestL = mid + axis * along * 0.97f + side * halfW * 0.85f, chestR = mid + axis * along * 0.97f - side * halfW * 0.85f;
            float y2 = c.y + height * 0.8f - 0.05f, y1 = c.y + height * 0.6f - 0.05f;
            Tube(v, uv, t, Line(new Vector3(chestL.x, y2, chestL.z), new Vector3(chestR.x, y1, chestR.z), axis * 0.05f), 0.024f, 5, false);
            Tube(v, uv, t, Line(new Vector3(chestR.x, y2, chestR.z), new Vector3(chestL.x, y1, chestL.z), axis * 0.06f), 0.024f, 5, false);
            Vector3 knot = mid + axis * along + side * halfW * 0.5f;
            knot.y = y1 - 0.04f;
            Tube(v, uv, t, new List<Vector3> { knot, knot + axis * 0.05f + side * 0.04f + Vector3.down * 0.18f, knot + axis * 0.04f + side * 0.09f + Vector3.down * 0.42f }, 0.022f, 5, false);
            Tube(v, uv, t, new List<Vector3> { knot, knot + axis * 0.06f - side * 0.02f + Vector3.down * 0.2f, knot + axis * 0.03f + side * 0.01f + Vector3.down * 0.5f }, 0.022f, 5, false);

            ropeMesh = new Mesh { name = "CuerdasDeSombra" };
            ropeMesh.SetVertices(v); ropeMesh.SetUVs(0, uv); ropeMesh.SetTriangles(t, 0);
            ropeMesh.RecalculateNormals();
            ropeMesh.RecalculateBounds();
            var go = new GameObject("Cuerdas");
            go.transform.SetParent(transform, false);
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);   // la malla ya está en coordenadas de mundo
            go.AddComponent<MeshFilter>().sharedMesh = ropeMesh;
            rope = go.AddComponent<MeshRenderer>();
            mat = new Material(sh) { name = "Nindo_ShadowRope" };
            mat.SetFloat(IdSeed, Random.Range(0f, 50f));
            rope.sharedMaterial = mat;
            rope.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;

            var lg = new GameObject("LuzVioleta");
            lg.transform.SetParent(transform, false);
            lg.transform.position = c + Vector3.up * height * 0.65f + axis * 0.7f;
            glow = lg.AddComponent<Light>();
            glow.type = LightType.Point; glow.color = GlowColor; glow.range = 3.6f; glow.intensity = glowBase;
            glow.shadows = LightShadows.None;
            motes = MakeMotes();
            Bound = true;
        }

        static List<Vector3> Line(Vector3 a, Vector3 b, Vector3 bulge)
        {
            var l = new List<Vector3>();
            for (int i = 0; i <= 6; i++) { float s = i / 6f; l.Add(Vector3.Lerp(a, b, s) + bulge * Mathf.Sin(s * Mathf.PI)); }
            return l;
        }

        /// <summary>Tubo facetado a lo largo de una polilínea; uv.x = metros recorridos (las hebras y los pulsos).</summary>
        void Tube(List<Vector3> v, List<Vector2> uv, List<int> t, List<Vector3> pts, float r, int sides, bool closed)
        {
            int m = pts.Count;
            int rings = closed ? m + 1 : m;
            int start = v.Count;
            float len = 0f;
            Vector3 prevN = Vector3.zero;
            for (int k = 0; k < rings; k++)
            {
                Vector3 pt = pts[k % m];
                Vector3 tan = closed ? (pts[(k + 1) % m] - pts[(k - 1 + m) % m]) : (pts[Mathf.Min(k + 1, m - 1)] - pts[Mathf.Max(k - 1, 0)]);
                tan.Normalize();
                Vector3 n = k == 0 ? Vector3.Cross(tan, Mathf.Abs(tan.y) > 0.9f ? Vector3.right : Vector3.up).normalized
                                   : (prevN - tan * Vector3.Dot(prevN, tan)).normalized;
                prevN = n;
                Vector3 bn = Vector3.Cross(tan, n);
                if (k > 0) len += Vector3.Distance(pts[(k - 1) % m], pt);
                for (int i = 0; i < sides; i++)
                {
                    float a = i * Mathf.PI * 2f / sides;
                    v.Add(pt + (n * Mathf.Cos(a) + bn * Mathf.Sin(a)) * r);
                    uv.Add(new Vector2(len, i / (float)sides));
                }
                path.Add(pt);
            }
            for (int k = 0; k < rings - 1; k++)
                for (int i = 0; i < sides; i++)
                {
                    int a0 = start + k * sides + i, a1 = start + k * sides + (i + 1) % sides;
                    int b0 = a0 + sides, b1 = a1 + sides;
                    t.AddRange(new[] { a0, a1, b0, a1, b1, b0 });
                }
            if (!closed)
            {
                // tapas: un abanico en cada punta
                int s0 = start, s1 = start + (rings - 1) * sides;
                for (int i = 1; i < sides - 1; i++)
                {
                    t.AddRange(new[] { s0, s0 + i + 1, s0 + i });
                    t.AddRange(new[] { s1, s1 + i, s1 + i + 1 });
                }
            }
        }

        ParticleSystem MakeMotes()
        {
            var ps = FXFactory.NewSystem("MotasVioletas", transform);
            var m = ps.main;
            m.loop = false; m.playOnAwake = false;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.8f, 1.6f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.1f, 0.4f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.04f, 0.09f);
            m.startColor = new ParticleSystem.MinMaxGradient(GlowColor, new Color(0.95f, 0.85f, 1f));
            m.gravityModifier = -0.25f;
            m.maxParticles = 300;
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.4f; noise.frequency = 1.1f;
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            return ps;
        }

        // ================================================================== API
        /// <summary>Las cuerdas se deshacen (borde encendido, motas que suben, la luz violeta se apaga): el abuelo está libre.</summary>
        public void Dissolve(float seconds = 1.6f)
        {
            if (!Bound) return;
            Bound = false;
            if (routine != null) StopCoroutine(routine);
            routine = StartCoroutine(DissolveRoutine(seconds));
            if (motes != null)
            {
                var ep = new ParticleSystem.EmitParams();
                for (int i = 0; i < path.Count; i += 2)
                {
                    ep.position = path[i];
                    ep.applyShapeToPosition = false;
                    motes.Emit(ep, 2);
                }
            }
            // en el abuelo (la raíz de las cuerdas es el centro de la arena, a 18 m)
            Game.Audio?.Play("shadow_rope_free", glow != null ? glow.transform.position : transform.position, 0.9f);
        }

        IEnumerator DissolveRoutine(float seconds)
        {
            float t = 0f;
            while (t < seconds)
            {
                t += Time.unscaledDeltaTime;
                dissolve = Mathf.Clamp01(t / seconds);
                yield return null;
            }
            dissolve = 1f;
            if (rope != null) rope.enabled = false;
            routine = null;
        }

        /// <summary>Atado de nuevo, ya (reintento antes de vencer a Kokuyō).</summary>
        public void Restore()
        {
            if (routine != null) { StopCoroutine(routine); routine = null; }
            dissolve = 0f;
            Bound = true;
            if (rope != null) rope.enabled = true;
            if (motes != null) motes.Clear();
        }

        void Update()
        {
            if (mat != null) mat.SetFloat(IdDissolve, dissolve);
            if (glow != null)
            {
                // late despacio, como algo que respira; se apaga con la disolución
                glow.intensity = glowBase * (0.8f + 0.2f * Mathf.Sin(Time.time * 1.7f)) * (1f - dissolve);
                glow.enabled = glow.intensity > 0.01f;
            }
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (ropeMesh != null) Destroy(ropeMesh);
        }
    }
}
