using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Lo que Kokuyō y su sombra dejan en el patio: las agujas de obsidiana (la grieta del Rompecascos, el estallido de
    /// Kage-nui), el charco de tinta del Paso de Sombra y el núcleo claro del Ichimonji (el lugar seguro bajo la
    /// empuñadura). Un objeto aparte del jefe (sus renderers no son del jefe: HitFlash y la sombra viva no los tocan) y
    /// todo con pool: nada se crea en medio de un golpe salvo la primera vez.
    /// </summary>
    public class KokuyoHazards : MonoBehaviour
    {
        class Needle { public Transform t; public Vector3 pos; public Quaternion rot; public float start, life, depth; public bool on; }

        static readonly string[] ShardProps = { "obsidian_shard_s", "obsidian_shard_m", "obsidian_shard_l" };
        static readonly Color InkPuddle = new Color(0.141f, 0.086f, 0.227f, 0.85f);    // #24163a
        static readonly Color CorePale = new Color(0.957f, 0.945f, 0.91f, 0.42f);       // #f4f1e8

        readonly List<Needle> shards = new List<Needle>(24);
        const int MaxShards = 24;
        const float ShardRise = 0.08f, ShardSink = 0.4f;
        Transform puddle, core;
        MeshRenderer puddleR, coreR;
        ParticleSystem bubbles;
        Material puddleMat, coreMat;
        Mesh coreMesh;

        public static KokuyoHazards Create(Transform parent)
        {
            var go = new GameObject("PeligrosDeKokuyo");
            go.transform.SetParent(parent, false);
            var h = go.AddComponent<KokuyoHazards>();
            h.Build();
            return h;
        }

        void Build()
        {
            // charco: un quad con el punto suave de las partículas teñido de tinta (borde difuso, sin textura nueva)
            puddleMat = FXMaterials.MakeParticle("CharcoDeTinta", false);
            FXMaterials.SetColor(puddleMat, InkPuddle);
            puddle = NewQuad("Charco", puddleMat, out puddleR);
            bubbles = FXFactory.NewSystem("Burbujas", transform);
            var m = bubbles.main;
            m.loop = true; m.duration = 1f; m.playOnAwake = false;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.4f, 0.8f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.4f, 1.4f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.12f, 0.3f);
            m.startColor = new Color(0.75f, 0.54f, 1f, 0.8f);
            m.gravityModifier = -0.2f;
            m.maxParticles = 60;
            var sh = bubbles.shape; sh.shapeType = ParticleSystemShapeType.Circle; sh.radius = 1.3f; sh.rotation = new Vector3(-90f, 0f, 0f);
            bubbles.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Additive;
            // núcleo seguro: disco nítido (el borde es la regla: adentro no te toca)
            coreMat = FXMaterials.MakeUnlitTransparent("NucleoSeguro", CorePale, false);
            coreMat.renderQueue = 3050;   // encima del aviso rojo del suelo
            coreMesh = Disc(32);
            var cg = new GameObject("NucleoSeguro");
            cg.transform.SetParent(transform, false);
            cg.AddComponent<MeshFilter>().sharedMesh = coreMesh;
            coreR = cg.AddComponent<MeshRenderer>();
            coreR.sharedMaterial = coreMat;
            coreR.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            coreR.receiveShadows = false;
            coreR.enabled = false;
            core = cg.transform;
        }

        Transform NewQuad(string name, Material mat, out MeshRenderer r)
        {
            var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
            Destroy(q.GetComponent<Collider>());
            q.name = name;
            q.transform.SetParent(transform, false);
            q.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
            r = q.GetComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.enabled = false;
            return q.transform;
        }

        static Mesh Disc(int n)
        {
            var v = new Vector3[n + 1];
            var t = new int[n * 3];
            v[0] = Vector3.zero;
            for (int i = 0; i < n; i++)
            {
                float a = i / (float)n * Mathf.PI * 2f;
                v[i + 1] = new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
                t[i * 3] = 0; t[i * 3 + 1] = 1 + (i + 1) % n; t[i * 3 + 2] = 1 + i;
            }
            var m = new Mesh { name = "Disco" };
            m.vertices = v; m.triangles = t;
            m.RecalculateNormals(); m.RecalculateBounds();
            return m;
        }

        void OnDestroy()
        {
            if (puddleMat != null) Destroy(puddleMat);
            if (coreMat != null) Destroy(coreMat);
            if (coreMesh != null) Destroy(coreMesh);
        }

        // ------------------------------------------------------------------ charco
        /// <summary>El charco de tinta donde se hundió (o por donde viaja): r = radio en metros, 0 lo apaga.</summary>
        public void Puddle(Vector3 pos, float radius)
        {
            bool on = radius > 0.05f;
            puddleR.enabled = on;
            if (!on) { if (bubbles.isPlaying) bubbles.Stop(true, ParticleSystemStopBehavior.StopEmitting); return; }
            puddle.position = pos + Vector3.up * 0.04f;
            puddle.localScale = new Vector3(radius * 2f, radius * 2f, 1f);
            bubbles.transform.position = pos + Vector3.up * 0.05f;
            var sh = bubbles.shape; sh.radius = radius * 0.8f;
            if (!bubbles.isPlaying) bubbles.Play();
        }

        /// <summary>El charco hierve más fuerte (el aviso de que está por salir).</summary>
        public void Boil(float rate)
        {
            var em = bubbles.emission; em.rateOverTime = rate;
        }

        // ------------------------------------------------------------------ núcleo seguro
        public void Core(Vector3 center, float radius)
        {
            bool on = radius > 0.05f;
            coreR.enabled = on;
            if (!on) return;
            core.position = center + Vector3.up * 0.08f;
            core.localScale = new Vector3(radius, 1f, radius);
        }

        // ------------------------------------------------------------------ agujas
        /// <summary>Una aguja de obsidiana sale del piso, queda 'life' s y se hunde. size 0..2 (chica, mediana, grande).</summary>
        public void Shard(Vector3 pos, int size, float life)
        {
            var s = Acquire(Mathf.Clamp(size, 0, 2));
            if (s == null) return;
            s.pos = pos;
            s.rot = Quaternion.Euler(Random.Range(-14f, 14f), Random.Range(0f, 360f), Random.Range(-14f, 14f));
            s.start = Time.time;
            s.life = life;
            s.on = true;
            s.t.gameObject.SetActive(true);
            Place(s, 0f);
        }

        Needle Acquire(int size)
        {
            string id = ShardProps[size];
            foreach (var s in shards) if (!s.on && s.t != null && s.t.name == id) return s;
            if (shards.Count >= MaxShards)
            {
                // pool lleno: se recicla la más vieja (ya se está hundiendo)
                Needle old = null;
                foreach (var s in shards) if (old == null || s.start < old.start) old = s;
                return old;
            }
            var prefab = Game.Content != null ? Game.Content.Prop(id) : null;
            if (prefab == null) return null;
            var go = Instantiate(prefab, transform);
            go.name = id;
            foreach (var c in go.GetComponentsInChildren<Collider>(true)) Destroy(c);
            foreach (var r in go.GetComponentsInChildren<Renderer>(true)) r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            float h = 1f;
            var rr = go.GetComponentInChildren<Renderer>();
            if (rr != null) h = Mathf.Max(0.3f, rr.bounds.size.y);
            var shard = new Needle { t = go.transform, depth = h + 0.1f };
            shards.Add(shard);
            return shard;
        }

        void Place(Needle s, float rise)
        {
            s.t.SetPositionAndRotation(s.pos + Vector3.down * s.depth * (1f - rise), s.rot);
        }

        public void ClearAll()
        {
            foreach (var s in shards) { s.on = false; if (s.t != null) s.t.gameObject.SetActive(false); }
            Puddle(Vector3.zero, 0f);
            Core(Vector3.zero, 0f);
        }

        void Update()
        {
            float now = Time.time;
            for (int i = 0; i < shards.Count; i++)
            {
                var s = shards[i];
                if (!s.on || s.t == null) continue;
                float age = now - s.start;
                float rise;
                if (age < ShardRise) rise = 1f - (1f - age / ShardRise) * (1f - age / ShardRise);
                else if (age < ShardRise + s.life) rise = 1f;
                else if (age < ShardRise + s.life + ShardSink) rise = 1f - (age - ShardRise - s.life) / ShardSink;
                else { s.on = false; s.t.gameObject.SetActive(false); continue; }
                Place(s, rise);
            }
        }
    }
}
