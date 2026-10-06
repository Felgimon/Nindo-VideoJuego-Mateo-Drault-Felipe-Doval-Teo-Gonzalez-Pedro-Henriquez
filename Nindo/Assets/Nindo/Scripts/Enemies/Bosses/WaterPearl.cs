using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Perla de agua de Mizuchi. Es el golpe desviable a distancia que enseña el parry perfecto:
    ///  * abanico / tormenta: el parry normal la revienta; el PERFECTO la devuelve dorada, buscando al koi, y al pegarle le
    ///    saca vida y le suma postura (como un parry de cerca). El dash la atraviesa.
    ///  * peloteo (Tama-asobi): una perla grande que cualquier parry devuelve; el koi la batea de vuelta (más rápida cada
    ///    vez) hasta que falla y le pega a él (queda varado), o hasta que Kaito falla.
    /// La fuente del golpe es la perla (no el jefe): un parry a 10 m no tiene que hacer retroceder al koi en pleno ataque.
    /// Avisa como todo el juego: anillo dorado a los pies de Kaito (ETA honesta, Boss.ProjectileEta), hyōshigi y destello.
    /// </summary>
    public class WaterPearl : MonoBehaviour
    {
        public enum Mode { Fan, Rally }

        public static readonly List<WaterPearl> Active = new List<WaterPearl>();
        static readonly Stack<WaterPearl> free = new Stack<WaterPearl>();
        static Material cyanMat, goldMat;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { Active.Clear(); free.Clear(); cyanMat = goldMat = null; }

        // agua de la paleta: glow_water #7ff0e0; devuelta, glow_spirit #ffd86b (el dorado del dragón del HUD)
        static readonly Color Cyan = new Color(0.5f, 0.94f, 0.88f);
        static readonly Color Gold = new Color(1f, 0.85f, 0.42f);
        const float SpeedCap = 16f;
        // cada vuelta del peloteo hacia Kaito dura al menos esto: el hyōshigi (0.38 s) siempre entra antes del golpe aunque
        // Kaito se acerque; a 16 m/s y 3 m la vuelta eran 0.11 s
        const float MinLeg = 0.55f;

        public MizuchiBoss Owner { get; private set; }
        public Mode Kind { get; private set; }
        /// <summary>Va hacia el koi (devuelta por Kaito).</summary>
        public bool TowardKoi { get; private set; }
        /// <summary>Ya sonó su aviso hacia Kaito en este tramo.</summary>
        [System.NonSerialized] public bool cued, glinted;
        public float Speed => speed;

        Vector3 dir;
        float speed, life, hitRadius, size, homing;
        float damage;
        float knockback;
        bool done, batQueued;
        Transform visual, shadow;
        MeshRenderer body;
        Light glow;
        TrailRenderer trail;
        MaterialPropertyBlock mpb;

        public static WaterPearl Spawn(MizuchiBoss owner, Mode mode, Vector3 pos, Vector3 dir, float speed, float size, float damage, float knockback)
        {
            WaterPearl p = null;
            while (p == null && free.Count > 0) p = free.Pop();
            if (p == null) p = Create();
            // primero la posición y después se prende: la estela no tiene que unir el lugar viejo con el nuevo
            p.transform.position = pos;
            p.gameObject.SetActive(true);
            p.Owner = owner; p.Kind = mode; p.TowardKoi = false;
            p.dir = dir.Flat().normalized; p.speed = speed; p.size = size;
            p.damage = damage; p.knockback = knockback;
            p.hitRadius = mode == Mode.Rally ? 1.2f : 1.0f;
            p.homing = mode == Mode.Rally ? 0.25f : 0f;
            p.life = mode == Mode.Rally ? 12f : 2.2f;
            p.done = false; p.batQueued = false; p.cued = false; p.glinted = false;
            p.visual.localScale = Vector3.one * size;
            p.SetColor(false);
            p.trail.Clear();
            p.trail.widthMultiplier = size * 0.9f;
            if (!Active.Contains(p)) Active.Add(p);
            Game.Audio?.Play("pearl_spit", pos, mode == Mode.Rally ? 1f : 0.7f, 0.08f);
            return p;
        }

        static WaterPearl Create()
        {
            var go = new GameObject("WaterPearl");
            var p = go.AddComponent<WaterPearl>();
            p.mpb = new MaterialPropertyBlock();
            var vis = new GameObject("Pearl");
            vis.transform.SetParent(go.transform, false);
            vis.AddComponent<MeshFilter>().sharedMesh = FallsAssets.Ico;
            p.body = vis.AddComponent<MeshRenderer>();
            p.body.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            p.visual = vis.transform;
            var lg = new GameObject("Glow");
            lg.transform.SetParent(go.transform, false);
            p.glow = lg.AddComponent<Light>();
            p.glow.type = LightType.Point; p.glow.range = 4f; p.glow.intensity = 3f; p.glow.shadows = LightShadows.None;
            p.trail = go.AddComponent<TrailRenderer>();
            p.trail.time = 0.22f;
            p.trail.minVertexDistance = 0.15f;
            p.trail.sharedMaterial = KoiWater.GlowLine;
            p.trail.widthCurve = new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(1f, 0f));
            p.trail.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            // sombra en el piso: con la cámara alta es lo que dice dónde va a estar la perla (está a 1.3 m del piso)
            var sh = new GameObject("Shadow");
            sh.transform.SetParent(go.transform, false);
            sh.AddComponent<MeshFilter>().sharedMesh = WaterSplash.Quad;
            var smr = sh.AddComponent<MeshRenderer>();
            smr.sharedMaterial = FXMaterials.Alpha;
            smr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            var smpb = new MaterialPropertyBlock();
            smpb.SetColor("_BaseColor", new Color(0.02f, 0.04f, 0.06f, 0.55f));
            smpb.SetColor("_Color", new Color(0.02f, 0.04f, 0.06f, 0.55f));
            smr.SetPropertyBlock(smpb);
            p.shadow = sh.transform;
            return p;
        }

        static Material PearlMat(bool gold)
        {
            if (gold) return goldMat != null ? goldMat : (goldMat = FXMaterials.MakeUnlitTransparent("PearlGold", new Color(Gold.r * 2.2f, Gold.g * 2.2f, Gold.b * 2.2f, 0.95f), true));
            return cyanMat != null ? cyanMat : (cyanMat = FXMaterials.MakeUnlitTransparent("PearlWater", new Color(Cyan.r * 1.8f, Cyan.g * 1.8f, Cyan.b * 1.8f, 0.9f), true));
        }

        void SetColor(bool gold)
        {
            body.sharedMaterial = PearlMat(gold);
            glow.color = gold ? Gold : Cyan;
            var c = gold ? Gold : Cyan;
            trail.startColor = new Color(c.r, c.g, c.b, 0.8f);
            trail.endColor = new Color(c.r, c.g, c.b, 0f);
        }

        // ------------------------------------------------------------------ ETA (avisos honestos)
        /// <summary>
        /// Segundos hasta que esta perla toque a Kaito (infinito si no va hacia él). Si va hacia el koi y él la va a
        /// batear, cuenta la vuelta entera: el anillo de los pies se cierra al ritmo del peloteo, no de golpe.
        /// </summary>
        public float EtaToPlayer(Vector3 player)
        {
            if (done) return float.PositiveInfinity;
            Vector3 pos = transform.position;
            if (!TowardKoi) return TimeToReach(pos, dir, speed, player, hitRadius, life);
            if (Kind != Mode.Rally || Owner == null || !Owner.RallyWillReturn) return float.PositiveInfinity;
            Vector3 snout = Owner.Snout;
            float toSnout = Mathf.Max(0f, CombatMath.FlatDistance(pos, snout) - 0.8f) / speed;
            float d = CombatMath.FlatDistance(snout, player);
            return toSnout + Mathf.Max(0f, d - hitRadius) / BackSpeed(d);
        }

        /// <summary>Velocidad de la vuelta hacia Kaito desde 'dist' m: +0.8 por golpe hasta 16 m/s, pero nunca menos de MinLeg s.</summary>
        float BackSpeed(float dist) => Mathf.Min(Mathf.Min(SpeedCap, speed + 0.8f), Mathf.Max(5f, (dist - hitRadius) / MinLeg));

        /// <summary>Tiempo hasta pasar a 'radius' de 'p' en línea recta (infinito si pasa de largo o se deshace antes).</summary>
        public static float TimeToReach(Vector3 from, Vector3 dir, float speed, Vector3 p, float radius, float life = 99f)
        {
            Vector3 d = (p - from).Flat();
            float along = Vector3.Dot(d, dir);
            float lat2 = d.sqrMagnitude - along * along;
            if (lat2 >= radius * radius) return float.PositiveInfinity;
            float reach = along - Mathf.Sqrt(radius * radius - lat2);
            if (reach < -radius) return float.PositiveInfinity;
            float t = Mathf.Max(0f, reach) / Mathf.Max(0.1f, speed);
            return t <= life ? t : float.PositiveInfinity;
        }

        public Vector3 Position => transform.position;

        // ------------------------------------------------------------------ vuelo
        void Update()
        {
            if (done) return;
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            var p = Game.Player;
            Vector3 pos = transform.position;
            // el peloteo busca un poco al que tiene que recibirla (no se la esquiva caminando de costado)
            if (homing > 0f)
            {
                Vector3 goal = TowardKoi && Owner != null ? Owner.Snout : p != null ? p.transform.position : pos + dir;
                Vector3 want = (goal - pos).Flat();
                if (want.sqrMagnitude > 0.04f) dir = Vector3.Slerp(dir, want.normalized, 1f - Mathf.Exp(-homing * 4f * dt)).Flat().normalized;
            }
            pos += dir * speed * dt;
            transform.position = pos;
            life -= dt;
            visual.localRotation = Quaternion.Euler(Time.time * 220f, Time.time * 140f, 0f);
            float deck = Owner != null ? Owner.DeckHeight : pos.y - 1.3f;
            shadow.position = new Vector3(pos.x, deck + 0.04f, pos.z);
            shadow.rotation = Quaternion.identity;
            float sh = 0.9f * size;
            shadow.localScale = new Vector3(sh, 1f, sh);
            glow.intensity = 2.6f + Mathf.Sin(Time.time * 18f) * 0.4f;

            if (TowardKoi) TickTowardKoi(pos);
            else if (p != null && p.IsAlive && CombatMath.FlatDistance(p.transform.position, pos) < hitRadius) TryHitPlayer(p);
            if (done) return;
            // fuera de la plataforma o vencida: revienta contra la baranda (el dash del peloteo termina acá)
            if (life <= 0f || Owner != null && CombatMath.FlatDistance(pos, Owner.arenaCenter) > MizuchiBoss.RailRadius + 1f) Burst(true);
        }

        void TryHitPlayer(PlayerController p)
        {
            var info = new DamageInfo
            {
                damage = damage, kind = AttackKind.Projectile, direction = dir, point = transform.position, knockback = knockback,
                sourceFaction = Faction.Enemy, source = this, attackName = Kind == Mode.Rally ? "Tama-asobi" : "Perla",
            };
            var r = p.ReceiveHit(info);
            switch (r)
            {
                case HitResult.Dodged:
                case HitResult.Ignored:
                    return;    // el dash la atraviesa: sigue de largo
                case HitResult.PerfectParry:
                    Reflect(true);
                    return;
                case HitResult.Parried:
                    if (Kind == Mode.Rally) Reflect(false);
                    else Burst(false);
                    return;
                default:
                    // golpe o guardia imperfecta: se deshace sobre Kaito
                    if (Kind == Mode.Rally) Owner?.OnRallyEnded(false);
                    Burst(false);
                    return;
            }
        }

        /// <summary>Kaito la devuelve: hacia el koi, dorada.</summary>
        void Reflect(bool perfect)
        {
            TowardKoi = true;
            cued = glinted = false;
            batQueued = false;
            speed = Kind == Mode.Rally ? Mathf.Min(SpeedCap, speed + 0.8f) : 14f;
            // la devuelta del abanico busca fuerte (si no, el parry perfecto de una perla de costado no llegaba nunca)
            if (Kind == Mode.Fan) homing = 1.2f;
            if (Owner != null) dir = (Owner.Snout - transform.position).Flat().normalized;
            else dir = -dir;
            SetColor(true);
            Game.Audio?.Play("pearl_ping", transform.position, 1f, 0.05f);
            Game.FX?.BladeGlint(transform.position, false);
            if (Kind == Mode.Rally && perfect) Owner?.OnRallyPerfect();
        }

        void TickTowardKoi(Vector3 pos)
        {
            if (Owner == null || !Owner.IsAlive) { Burst(true); return; }
            Vector3 snout = Owner.Snout;
            float d = CombatMath.FlatDistance(pos, snout);
            if (Kind == Mode.Rally && Owner.RallyWillReturn)
            {
                // el koi arranca el revés 0.17 s antes (el golpe de hocico del clip 'Return' cae en el cuadro 5)
                if (!batQueued && (d - 0.8f) / speed <= MizuchiBoss.ReturnLead) { batQueued = true; Owner.OnRallyIncoming(); }
                if (d <= 0.8f + speed * Time.deltaTime)
                {
                    TowardKoi = false; batQueued = false; cued = glinted = false;
                    var p = Game.Player;
                    if (p != null)
                    {
                        dir = (p.transform.position - pos).Flat().normalized;
                        speed = BackSpeed(CombatMath.FlatDistance(p.transform.position, pos));
                    }
                    SetColor(false);
                    Owner.OnRallyBatted(this);
                }
                return;
            }
            // le pega al cuerpo (cualquier parte de la silueta)
            Vector3 hc = Owner.HurtCenter(pos);
            if (CombatMath.FlatDistance(pos, hc) <= Owner.Radius + 0.2f)
            {
                if (Kind == Mode.Rally) Owner.OnRallyMissed(this);
                else Owner.OnPearlReturned(this);
                Burst(false);
            }
        }

        /// <summary>Revienta (pegó, la desviaron o chocó con la baranda).</summary>
        public void Burst(bool rail)
        {
            if (done) return;
            done = true;
            Active.Remove(this);
            WaterSplash.Flop(transform.position, Kind == Mode.Rally ? 0.6f : 0.35f);
            Game.Audio?.Play("pearl_pop", transform.position, 0.8f, 0.08f);
            if (rail && Kind == Mode.Rally) Owner?.OnRallyEnded(false);
            gameObject.SetActive(false);
            free.Push(this);
        }

        /// <summary>Saca todas las perlas de un jefe sin ruido (reintento, cambio de fase, muerte).</summary>
        public static void ClearAll(MizuchiBoss owner)
        {
            for (int i = Active.Count - 1; i >= 0; i--)
            {
                var p = Active[i];
                if (p == null) { Active.RemoveAt(i); continue; }
                if (p.Owner != owner) continue;
                p.done = true;
                Active.RemoveAt(i);
                p.gameObject.SetActive(false);
                free.Push(p);
            }
        }

        void OnDisable() { Active.Remove(this); }
    }
}
