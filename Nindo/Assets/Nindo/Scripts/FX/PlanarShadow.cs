using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Sombra viva de un personaje (Kokuyō, "la sombra que se mueve primero"). Es un DOBLE de su modelo (mismos
    /// huesos y mallas) dibujado con Nindo/ShadowInk: cada vértice se proyecta al piso a lo largo de la luna y la
    /// silueta queda estirada ~6 m hacia la cámara sobre las losas claras del patio, en tinta violeta viva.
    /// El doble es un objeto aparte (nunca hijo del jefe: Enemy busca su Animator y Boss apaga sus renderers con
    /// GetComponentsInChildren).
    ///  - Espejo (por defecto): copia la pose de los huesos del cuerpo en cada LateUpdate, cruces de animación incluidos.
    ///  - Adelantada (Lead): el doble anima con su propio Animator (mismo controller) y quien la maneja lo muestrea
    ///    más adelante en el clip con SampleAhead: la sombra actúa el golpe 0.36 s antes que el cuerpo.
    ///  - Suelta (Detach): deja de seguir al cuerpo y Root se mueve libre (Kage, la sombra arrancada); RiseTo la
    ///    despega del piso y la para como figura de humo de tinta.
    /// El cuerpo no proyecta su sombra real mientras tanto (si no, se ven dos sombras distintas).
    /// </summary>
    [DefaultExecutionOrder(900)]
    public class PlanarShadow : MonoBehaviour
    {
        /// <summary>Luz de la sombra: desde el norte, 35° sobre el horizonte (hacia la cámara). 4.2 m de alto dan 6 m de sombra.</summary>
        public static readonly Vector3 DefaultLight = new Vector3(0f, -0.574f, -0.819f);
        public static readonly Color InkColor = new Color(0.141f, 0.086f, 0.227f);      // #24163a
        public static readonly Color PulseColor = new Color(0.227f, 0.078f, 0.376f);    // #3a1460

        static readonly int IdLight = Shader.PropertyToID("_LightDir"), IdGround = Shader.PropertyToID("_GroundY"),
            IdOrigin = Shader.PropertyToID("_Origin"), IdArena = Shader.PropertyToID("_ArenaCenter"), IdHole = Shader.PropertyToID("_Hole"),
            IdPulse = Shader.PropertyToID("_Pulse"), IdRise = Shader.PropertyToID("_Rise"), IdFade = Shader.PropertyToID("_Fade"),
            IdColor = Shader.PropertyToID("_Color"), IdPulseColor = Shader.PropertyToID("_PulseColor"), IdStretch = Shader.PropertyToID("_Stretch");
        static readonly string[] WeaponNames = { "Katana", "katana", "Isan", "Nodachi", "Martillo", "Arma" };

        /// <summary>El Animator del doble (mismo controller que el cuerpo): lo maneja quien adelanta la sombra.</summary>
        public Animator ShadowAnimator => doubleAnim;
        /// <summary>Raíz del doble: sigue al cuerpo salvo después de Detach (ahí se mueve libre).</summary>
        public Transform Root => doubleRoot;
        public bool Detached { get; private set; }
        /// <summary>Alto del cuerpo en reposo (m): normaliza el hervor y la levantada.</summary>
        public float BodyHeight { get; private set; } = 2f;
        /// <summary>Radio del hueco alrededor de Kaito (el lazo de la bandana empuja la tinta).</summary>
        public float HoleRadius = 1.1f;
        /// <summary>El hueco sigue a Kaito; si es false, lo ubica SetHole.</summary>
        public bool HoleFollowsPlayer = true;
        /// <summary>Multiplicador del largo de la sombra (1 = el que da la luz).</summary>
        public float Stretch = 1f;

        Transform body, holder, doubleRoot, bladeTip;
        Animator doubleAnim;
        Material mat;
        readonly List<(Transform src, Transform dst)> bones = new List<(Transform, Transform)>();
        readonly List<(GameObject src, GameObject dst)> parts = new List<(GameObject, GameObject)>();
        readonly List<(Renderer src, Renderer dst)> rends = new List<(Renderer, Renderer)>();
        readonly List<(Renderer r, ShadowCastingMode mode)> suppressed = new List<(Renderer, ShadowCastingMode)>();
        Renderer bladeProxy;
        ParticleSystem smoke, splash;
        Vector3 lightDir = DefaultLight, holePos, arenaCenter;
        float arenaRadius = 19f, groundY, pulse, pulseLen = 0.16f;
        float rise, riseFrom, riseTo, riseT = 1f, riseDur;
        float fade = 1f, fadeFrom = 1f, fadeTo = 1f, fadeT = 1f, fadeDur;
        bool lead;

        // ================================================================== creación
        /// <summary>
        /// Crea la sombra viva de un cuerpo animado. body = el Animator del modelo (el hijo "Model" del enemigo).
        /// arenaRadius recorta la tinta (el patio mide 18.5 m; afuera, escaleras y pasto, no se dibuja).
        /// Devuelve null si el shader no compila en esta plataforma (el combate sigue, sin la sombra).
        /// </summary>
        public static PlanarShadow Create(Animator body, Vector3 arenaCenter, float arenaRadius, bool suppressBodyShadow = true, float bladeWidth = 0.5f)
        {
            if (body == null) return null;
            var sh = Resources.Load<Shader>("Shaders/NindoShadowInk");
            if (sh == null || !sh.isSupported)
            {
                Debug.LogWarning("[Nindo] No compila Nindo/ShadowInk: la sombra viva queda desactivada.");
                return null;
            }
            // el doble se arma inactivo: así no corre el Awake de los scripts que trae el modelo (y se borran antes)
            var holder = new GameObject("Sombra_" + body.transform.root.name);
            holder.SetActive(false);
            var clone = Instantiate(body.gameObject, holder.transform);
            clone.name = "Doble";
            var ps = holder.AddComponent<PlanarShadow>();
            ps.Build(body, holder.transform, clone, sh, arenaCenter, arenaRadius, bladeWidth);
            if (suppressBodyShadow) ps.SuppressBodyShadow();
            holder.SetActive(true);
            return ps;
        }

        /// <summary>Lo mismo partiendo de la malla del cuerpo: busca el Animator que la mueve (sus huesos cuelgan de él).</summary>
        public static PlanarShadow Create(SkinnedMeshRenderer mesh, Vector3 arenaCenter, float arenaRadius, bool suppressBodyShadow = true, float bladeWidth = 0.5f)
        {
            var anim = mesh != null ? mesh.GetComponentInParent<Animator>() : null;
            if (anim == null && mesh != null) Debug.LogWarning("[Nindo] PlanarShadow: " + mesh.name + " no cuelga de un Animator.");
            return Create(anim, arenaCenter, arenaRadius, suppressBodyShadow, bladeWidth);
        }

        void Build(Animator src, Transform holderT, GameObject clone, Shader sh, Vector3 center, float radius, float bladeWidth)
        {
            body = src.transform;
            holder = holderT;
            doubleRoot = clone.transform;
            // ya en su lugar: si se crea después de este LateUpdate, el primer cuadro no la dibuja en el origen
            doubleRoot.SetPositionAndRotation(body.position, body.rotation);
            doubleRoot.localScale = body.lossyScale;
            arenaCenter = center;
            arenaRadius = radius;
            // pares cuerpo -> doble recorriendo las dos jerarquías en paralelo (el clon es idéntico ahora)
            Pair(body, doubleRoot);
            // fuera todo lo que no sea huesos y mallas: scripts, colisiones, luces, partículas, estelas, audio
            foreach (var c in clone.GetComponentsInChildren<MonoBehaviour>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<Collider>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<Light>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<AudioSource>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<TrailRenderer>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<LineRenderer>(true)) DestroyImmediate(c);
            foreach (var c in clone.GetComponentsInChildren<ParticleSystem>(true)) if (c != null) DestroyImmediate(c.gameObject);
            bones.RemoveAll(p => p.dst == null);
            parts.RemoveAll(p => p.dst == null);
            rends.RemoveAll(p => p.dst == null);

            doubleAnim = clone.GetComponent<Animator>();
            if (doubleAnim != null)
            {
                doubleAnim.applyRootMotion = false;
                doubleAnim.fireEvents = false;               // los eventos de los clips son del cuerpo, no de su sombra
                doubleAnim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                doubleAnim.enabled = false;                  // en espejo los huesos los copia LateUpdate
            }

            mat = new Material(sh) { name = "Nindo_ShadowInk_" + body.root.name };
            mat.SetColor(IdColor, InkColor);
            mat.SetColor(IdPulseColor, PulseColor);
            BodyHeight = MeasureHeight(src);
            groundY = GroundBelow(body.position);
            foreach (var p in rends) Dress(p.dst);
            bladeProxy = MakeBladeProxy(clone.transform, bladeWidth);
            smoke = MakeSmoke();
            splash = MakeSplash();
            Apply();
        }

        void Pair(Transform a, Transform b)
        {
            bones.Add((a, b));
            parts.Add((a.gameObject, b.gameObject));
            var ra = a.GetComponent<Renderer>();
            var rb = b.GetComponent<Renderer>();
            if (ra != null && rb != null && (ra is SkinnedMeshRenderer || ra is MeshRenderer)) rends.Add((ra, rb));
            int n = Mathf.Min(a.childCount, b.childCount);
            for (int i = 0; i < n; i++) Pair(a.GetChild(i), b.GetChild(i));
        }

        /// <summary>Todo el doble con la tinta: sin sombras ni sondas, y con bounds enormes (la sombra proyectada
        /// cae lejos de la malla real y el frustum culling la cortaría cuando el jefe sale de cuadro).</summary>
        void Dress(Renderer r)
        {
            int n = r.sharedMaterials.Length;
            if (r is SkinnedMeshRenderer smrN && smrN.sharedMesh != null) n = Mathf.Max(n, smrN.sharedMesh.subMeshCount);
            else if (r.GetComponent<MeshFilter>() is MeshFilter mfN && mfN.sharedMesh != null) n = Mathf.Max(n, mfN.sharedMesh.subMeshCount);
            var arr = new Material[Mathf.Max(1, n)];
            for (int i = 0; i < arr.Length; i++) arr[i] = mat;
            r.sharedMaterials = arr;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
            r.allowOcclusionWhenDynamic = false;
            Transform space = r is SkinnedMeshRenderer smr && smr.rootBone != null ? smr.rootBone : r.transform;
            float s = Mathf.Max(1e-4f, Mathf.Abs(space.lossyScale.x));
            r.localBounds = new Bounds(Vector3.zero, Vector3.one * (60f / s));
        }

        static float MeasureHeight(Animator a)
        {
            bool any = false;
            Bounds b = default;
            foreach (var r in a.GetComponentsInChildren<Renderer>())
            {
                if (!(r is SkinnedMeshRenderer || r is MeshRenderer) || !r.enabled) continue;
                if (!any) { b = r.bounds; any = true; } else b.Encapsulate(r.bounds);
            }
            return any ? Mathf.Max(0.5f, b.max.y - a.transform.position.y) : 2f;
        }

        static float GroundBelow(Vector3 p)
        {
            // las losas del patio (y el terreno) tienen collider en la capa Default
            return Physics.Raycast(p + Vector3.up * 1.5f, Vector3.down, out var hit, 6f, LayerMask.GetMask("Default"), QueryTriggerInteraction.Ignore)
                ? hit.point.y : p.y;
        }

        /// <summary>
        /// La hoja real da una sombra de un pelo (es fina vista desde la luna): una cruz de dos láminas a lo largo de
        /// la hoja, solo para la sombra, hace que el tajo se lea en el piso.
        /// </summary>
        Renderer MakeBladeProxy(Transform root, float width)
        {
            Transform basePt = Find(root, "KatanaBase"), tipPt = Find(root, "KatanaTip");
            if ((basePt == null || tipPt == null) && !KatanaRig.Find(root, WeaponNames, out basePt, out tipPt)) return null;
            bladeTip = tipPt;
            Transform w = basePt.parent;
            Vector3 a = basePt.localPosition, b = tipPt.localPosition;
            Vector3 axis = b - a;
            if (axis.sqrMagnitude < 1e-8f) return null;
            Vector3 u = Vector3.Cross(axis, Mathf.Abs(Vector3.Dot(axis.normalized, Vector3.up)) > 0.9f ? Vector3.right : Vector3.up).normalized;
            Vector3 v = Vector3.Cross(axis, u).normalized;
            float s = Mathf.Max(1e-4f, Mathf.Abs(w.lossyScale.x));
            float hw = width * 0.5f / s;
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var tris = new List<int>();
            foreach (var (side, n) in new[] { (u, v), (v, u) })
            {
                int k = verts.Count;
                verts.Add(a - side * hw); verts.Add(a + side * hw); verts.Add(b + side * hw * 0.35f); verts.Add(b - side * hw * 0.35f);
                for (int i = 0; i < 4; i++) norms.Add(n);
                tris.AddRange(new[] { k, k + 1, k + 2, k, k + 2, k + 3 });
            }
            var mesh = new Mesh { name = "SombraHoja" };
            mesh.SetVertices(verts); mesh.SetNormals(norms); mesh.SetTriangles(tris, 0);
            mesh.RecalculateBounds();
            var go = new GameObject("SombraHoja");
            go.transform.SetParent(w, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            Dress(mr);
            return mr;
        }

        static Transform Find(Transform root, string name)
        {
            foreach (var t in root.GetComponentsInChildren<Transform>(true)) if (t.name == name) return t;
            return null;
        }

        /// <summary>Humo de tinta que sube de la figura cuando está parada (Kage). Caja del tamaño del cuerpo: no
        /// depende de que la malla sea legible.</summary>
        ParticleSystem MakeSmoke()
        {
            var ps = FXFactory.NewSystem("HumoDeTinta", holder);
            var m = ps.main;
            m.loop = true; m.duration = 2f; m.playOnAwake = true;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.9f, 1.6f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.2f, 0.7f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.25f * BodyHeight / 4.5f + 0.2f, 0.6f * BodyHeight / 4.5f + 0.35f);
            m.startColor = new Color(0.12f, 0.07f, 0.2f, 0.55f);
            m.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            m.gravityModifier = -0.12f;
            m.maxParticles = 120;
            var em = ps.emission; em.rateOverTime = 0f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box;
            sh.scale = new Vector3(BodyHeight * 0.35f, BodyHeight * 0.9f, BodyHeight * 0.25f);
            sh.position = new Vector3(0f, BodyHeight * 0.45f, 0f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.5f; noise.frequency = 0.6f;
            var sol = ps.sizeOverLifetime; sol.enabled = true;
            sol.size = new ParticleSystem.MinMaxCurve(1f, new AnimationCurve(new Keyframe(0f, 0.5f), new Keyframe(1f, 1.4f)));
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(new Color(0.75f, 0.55f, 1f), 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.2f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            ps.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
            ps.Play();
            return ps;
        }

        /// <summary>Salpicón de tinta en la punta de la sombra cuando "golpea" (Strike).</summary>
        ParticleSystem MakeSplash()
        {
            var ps = FXFactory.NewSystem("SalpiconDeTinta", holder);
            var m = ps.main;
            m.loop = false; m.playOnAwake = false;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.25f, 0.5f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(2f, 5.5f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.08f, 0.2f);
            m.startColor = new Color(0.16f, 0.08f, 0.26f, 0.9f);
            m.gravityModifier = 1.6f;
            m.maxParticles = 80;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Hemisphere; sh.radius = 0.15f;
            sh.rotation = new Vector3(-90f, 0f, 0f);
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = FXMaterials.Alpha;
            r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.05f; r.lengthScale = 1.2f;
            return ps;
        }

        // ================================================================== API
        /// <summary>
        /// Muestrea el doble en otro punto del clip (la sombra adelantada): pasa a modo Lead si no lo estaba.
        /// Ej.: SampleAhead(hashDelPaso, normDelCuerpo + 0.36 / largoDelClip).
        /// </summary>
        public void SampleAhead(int stateHash, float normalizedTime, int layer = 0)
        {
            if (doubleAnim == null) return;
            Lead = true;
            doubleAnim.Play(stateHash, layer, normalizedTime);
            doubleAnim.Update(0f);
        }

        public void SampleAhead(string state, float normalizedTime, int layer = 0) => SampleAhead(Animator.StringToHash(state), normalizedTime, layer);

        /// <summary>true: el doble anima solo (SampleAhead); false: copia la pose del cuerpo (espejo exacto).</summary>
        public bool Lead
        {
            get => lead;
            set
            {
                if (lead == value || doubleAnim == null) return;
                lead = value;
                doubleAnim.enabled = value;
                if (value)
                {
                    doubleAnim.Rebind();
                    doubleAnim.speed = 0f;                   // la pose la fija SampleAhead; no avanza sola
                }
            }
        }

        /// <summary>
        /// La sombra "golpea": un instante más saturada y brillante, salpicón de tinta en la punta de la hoja y el
        /// susurro (sonido "kokuyo_whisper"). Es el QUÉ del golpe: llega 0.36 s antes que el cuerpo.
        /// </summary>
        public void Strike(float seconds = 0.16f)
        {
            pulse = 1f;
            pulseLen = Mathf.Max(0.04f, seconds);
            Vector3 tip = bladeTip != null ? ProjectToGround(bladeTip.position) : ProjectToGround(doubleRoot.position + Vector3.up * BodyHeight * 0.6f);
            if (splash != null)
            {
                splash.transform.position = tip;
                splash.Emit(26);
            }
            Game.Audio?.Play("kokuyo_whisper", tip, 0.9f);
        }

        /// <summary>Dónde cae en el piso, según la luz de la sombra, un punto del cuerpo (p. ej. la punta de la espada).</summary>
        public Vector3 ProjectToGround(Vector3 p)
        {
            Vector3 L = LightNormalized();
            float h = Mathf.Max(0f, p.y - groundY);
            return new Vector3(p.x + L.x / -L.y * h * Stretch, groundY + 0.05f, p.z + L.z / -L.y * h * Stretch);
        }

        /// <summary>Largo de la sombra del cuerpo parado (m).</summary>
        public float Length { get { Vector3 L = LightNormalized(); return BodyHeight * new Vector2(L.x, L.z).magnitude / -L.y * Stretch; } }

        /// <summary>Dirección en la que viaja la luz de la sombra (no hace falta normalizarla).</summary>
        public void SetLightDirection(Vector3 travel) { if (travel.sqrMagnitude > 1e-6f) lightDir = travel; }

        public void SetHole(Vector3 pos, float radius) { holePos = pos; HoleRadius = radius; }

        /// <summary>Despega la sombra del piso (1 = figura de humo parada) o la vuelve a acostar (0).</summary>
        public void RiseTo(float target, float seconds)
        {
            riseFrom = rise; riseTo = Mathf.Clamp01(target); riseDur = Mathf.Max(0f, seconds); riseT = 0f;
            if (riseDur <= 0f) { rise = riseTo; riseT = 1f; }
        }

        public float Rise => rise;

        /// <summary>Aparece / se desvanece (la tinta se seca o vuelve a correr).</summary>
        public void FadeTo(float alpha, float seconds)
        {
            fadeFrom = fade; fadeTo = Mathf.Clamp01(alpha); fadeDur = Mathf.Max(0f, seconds); fadeT = 0f;
            if (fadeDur <= 0f) { fade = fadeTo; fadeT = 1f; }
        }

        public void SetVisible(bool v) => FadeTo(v ? 1f : 0f, 0f);

        /// <summary>Suelta la sombra: Root deja de seguir al cuerpo (se mueve libre). Sigue copiando su pose salvo en Lead.</summary>
        public void Detach() => Detached = true;

        /// <summary>La sombra vuelve a los pies del cuerpo.</summary>
        public void Reattach() => Detached = false;

        /// <summary>Saca la sombra y le devuelve al cuerpo su sombra real.</summary>
        public void Release()
        {
            RestoreBodyShadow();
            if (holder != null) Destroy(holder.gameObject);
        }

        void SuppressBodyShadow()
        {
            foreach (var p in rends)
            {
                if (p.src == null) continue;
                suppressed.Add((p.src, p.src.shadowCastingMode));
                p.src.shadowCastingMode = ShadowCastingMode.Off;
            }
        }

        void RestoreBodyShadow()
        {
            foreach (var s in suppressed) if (s.r != null) s.r.shadowCastingMode = s.mode;
            suppressed.Clear();
        }

        void OnDestroy()
        {
            RestoreBodyShadow();
            if (mat != null) Destroy(mat);
        }

        // ================================================================== cada frame
        Vector3 LightNormalized()
        {
            Vector3 L = lightDir.normalized;
            if (L.y > -0.08f) { L.y = -0.08f; L.Normalize(); }
            return L;
        }

        void LateUpdate()
        {
            if (body == null) { if (!Detached) { Release(); return; } }
            else if (!Detached)
            {
                doubleRoot.SetPositionAndRotation(body.position, body.rotation);
                doubleRoot.localScale = body.lossyScale;
            }
            if (body != null)
            {
                if (!lead)
                {
                    // espejo: la pose exacta del cuerpo (índice 0 = raíz, ya ubicada arriba)
                    for (int i = 1; i < bones.Count; i++)
                    {
                        var (s, d) = bones[i];
                        if (s == null || d == null) continue;
                        d.localPosition = s.localPosition;
                        d.localRotation = s.localRotation;
                        d.localScale = s.localScale;
                    }
                }
                // piezas que el jefe apaga (hombrera rota, máscara que cae) y modelo escondido (teletransporte)
                for (int i = 1; i < parts.Count; i++)
                {
                    var (s, d) = parts[i];
                    if (s != null && d != null && d.activeSelf != s.activeSelf) d.SetActive(s.activeSelf);
                }
                bool bodyShown = body.gameObject.activeInHierarchy;
                foreach (var (s, d) in rends) if (s != null && d != null) d.enabled = s.enabled && bodyShown;
            }
            float dt = Time.deltaTime;
            if (riseT < 1f) { riseT = riseDur > 0f ? Mathf.Clamp01(riseT + dt / riseDur) : 1f; rise = Mathf.Lerp(riseFrom, riseTo, Mathf.SmoothStep(0f, 1f, riseT)); }
            if (fadeT < 1f) { fadeT = fadeDur > 0f ? Mathf.Clamp01(fadeT + dt / fadeDur) : 1f; fade = Mathf.Lerp(fadeFrom, fadeTo, fadeT); }
            pulse = Mathf.Max(0f, pulse - dt / pulseLen);
            if (bladeProxy != null) bladeProxy.enabled = rise < 0.3f && fade > 0.01f;
            if (smoke != null)
            {
                smoke.transform.SetPositionAndRotation(doubleRoot.position, doubleRoot.rotation);
                var em = smoke.emission; em.rateOverTime = 40f * Mathf.Clamp01((rise - 0.3f) / 0.7f) * fade;
            }
            if (HoleFollowsPlayer && Game.Player != null) holePos = Game.Player.transform.position;
            Apply();
        }

        void Apply()
        {
            if (mat == null) return;
            Vector3 o = doubleRoot != null ? doubleRoot.position : transform.position;
            mat.SetVector(IdLight, LightNormalized());
            mat.SetFloat(IdGround, groundY);
            mat.SetFloat(IdStretch, Stretch);
            mat.SetVector(IdOrigin, new Vector4(o.x, groundY, o.z, BodyHeight));
            mat.SetVector(IdArena, new Vector4(arenaCenter.x, arenaCenter.y, arenaCenter.z, arenaRadius));
            mat.SetVector(IdHole, new Vector4(holePos.x, holePos.y, holePos.z, HoleRadius));
            mat.SetFloat(IdPulse, pulse * pulse);
            mat.SetFloat(IdRise, rise);
            mat.SetFloat(IdFade, fade);
        }
    }
}
