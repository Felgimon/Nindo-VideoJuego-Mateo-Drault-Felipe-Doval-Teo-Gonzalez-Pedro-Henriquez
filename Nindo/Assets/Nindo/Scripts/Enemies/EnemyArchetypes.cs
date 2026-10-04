using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Presets de enemigos y jefes. Los nombres de estado coinciden con los AnimatorControllers
    /// generados en Assets/Nindo/Animation. Tiempos normalizados (0..1) respecto del clip.
    /// </summary>
    public static class EnemyArchetypes
    {
        static AttackDef Hit(string state, float dmg, float aStart, float aEnd, float range = 2.3f, float arc = 110f,
            AttackKind kind = AttackKind.Light, float lunge = 0.8f, float telegraph = 0f, float speed = 1f, float kb = 0.6f)
        {
            return new AttackDef
            {
                name = state, state = state, damage = dmg, activeStart = aStart, activeEnd = aEnd, range = range, arc = arc,
                kind = kind, lunge = lunge, lungeStart = Mathf.Max(0f, aStart - 0.25f), lungeEnd = aStart + 0.05f,
                telegraph = telegraph, speed = speed, knockback = kb, hitStop = kind == AttackKind.Light ? 0.07f : 0.12f,
                timing = AttackDef.Snappy(0.85f, 1.35f, aStart, 1f), sfx = kind == AttackKind.Light ? "enemy_swing" : "enemy_swing_heavy",
            };
        }

        public static EnemyConfig Get(string id)
        {
            switch (id)
            {
                case "ninja": return Ninja();
                case "ninja_elite": return NinjaElite();
                case "sumo": return Sumo();
                case "sumo_mountain": return SumoMountain();
                case "goro": return Goro();
                case "mizuchi": return Mizuchi();
                case "ozeki": return Ozeki();
                case "kage": return Kage();
                case "kage_clone": return KageClone();
                default:
                    Debug.LogWarning($"[Nindo] Arquetipo desconocido '{id}', uso ninja.");
                    return Ninja();
            }
        }

        // ------------------------------------------------------------------ comunes
        public static EnemyConfig Ninja()
        {
            var c = new EnemyConfig
            {
                id = "ninja", displayName = "Ninja del Clan", maxHealth = 60, runSpeed = 5.0f, walkSpeed = 2.0f,
                radius = 0.42f, height = 1.7f, scale = 1f, maxImbalance = 3, exhaustedTime = 3.2f, guardTime = 1.4f,
                poiseHits = 2, preferredDistance = 3.4f, detectRadius = 10f,
                animGuard = "Guard", animCounter = "Counter", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Spotted", animDeath = "Death", animParried = "Hit",
            };
            var a1 = Hit("Attack1", 12, 0.6f, 0.78f, telegraph: 0.12f);
            var a2 = Hit("Attack2", 12, 0.42f, 0.62f);
            var a3 = Hit("Attack3", 15, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.4f, kb: 1.2f);
            c.patterns = new[]
            {
                new AttackPattern { name = "Combo de 3", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 2.8f },
                new AttackPattern { name = "Doble", steps = new[] { a1, a2 }, weight = 1.5f, maxRange = 2.8f },
                new AttackPattern { name = "Estocada", steps = new[] { Hit("Attack3", 16, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 3.2f, range: 2.6f) }, weight = 1f, minRange = 2.6f, maxRange = 5.5f, cooldown = 4f },
            };
            return c;
        }

        public static EnemyConfig NinjaElite()
        {
            var c = Ninja();
            c.id = "ninja_elite"; c.displayName = "Ninja de Élite";
            c.maxHealth = 90; c.runSpeed = 5.6f; c.maxImbalance = 4; c.guardTime = 1.8f; c.poiseHits = 1;
            c.tint = new Color(0.75f, 0.18f, 0.15f); c.tintStrength = 0.55f;
            foreach (var p in c.patterns) foreach (var s in p.steps) { s.damage *= 1.25f; s.speed *= 1.12f; }
            var a1 = Hit("Attack1", 14, 0.6f, 0.78f, telegraph: 0.1f, speed: 1.12f);
            var a2 = Hit("Attack2", 14, 0.42f, 0.62f, speed: 1.12f);
            var a3 = Hit("Attack3", 18, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.4f, speed: 1.1f);
            var list = new System.Collections.Generic.List<AttackPattern>(c.patterns);
            list.Add(new AttackPattern { name = "Combo largo", steps = new[] { a1, a2, a1, a3 }, weight = 1.2f, maxRange = 2.8f });
            c.patterns = list.ToArray();
            return c;
        }

        public static EnemyConfig Sumo()
        {
            var c = new EnemyConfig
            {
                id = "sumo", displayName = "Luchador de Sumo", maxHealth = 150, runSpeed = 3.4f, walkSpeed = 1.6f, turnSpeed = 6f,
                radius = 0.85f, height = 2.5f, scale = 1f, maxImbalance = 2, exhaustedTime = 3.8f, guardTime = 0.8f,
                poiseHits = 4, hyperArmor = true, knockbackResist = 0.7f, preferredDistance = 3.6f, detectRadius = 11f,
                staggerTime = 0.25f,
                animGuard = "Idle", animCounter = "Attack1", animExhausted = "Exhausted", animHit = "Hit",
                animSpotted = "Spotted", animDeath = "Exhausted", animParried = "Hit",
            };
            var slap1 = Hit("Attack1", 18, 0.7f, 0.9f, range: 2.8f, arc: 120, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f);
            var slap2 = Hit("Attack2", 20, 0.6f, 0.82f, range: 2.8f, arc: 130, kind: AttackKind.Heavy, lunge: 0.6f, kb: 1.6f);
            var stomp = Hit("Attack3", 26, 0.8f, 0.92f, range: 3.4f, arc: 360, kind: AttackKind.Heavy, lunge: 0.2f, kb: 2.2f);
            var charge = Hit("Special", 30, 0.35f, 0.85f, range: 2.4f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.45f, kb: 3f);
            charge.special = "charge"; charge.specialParam = 11f; charge.tracking = true;
            c.patterns = new[]
            {
                new AttackPattern { name = "Bofetadas", steps = new[] { slap1, slap2 }, weight = 2f, maxRange = 3.2f },
                new AttackPattern { name = "Pisotón", steps = new[] { stomp }, weight = 1f, maxRange = 3.4f, cooldown = 3f },
                new AttackPattern { name = "Embestida imparable", steps = new[] { charge }, weight = 1.4f, minRange = 3.5f, maxRange = 11f, cooldown = 5f },
            };
            return c;
        }

        public static EnemyConfig SumoMountain()
        {
            var c = Sumo();
            c.id = "sumo_mountain"; c.displayName = "Sumo de la Montaña";
            c.maxHealth = 200; c.tint = new Color(0.35f, 0.45f, 0.75f); c.tintStrength = 0.45f;
            foreach (var p in c.patterns) foreach (var s in p.steps) s.damage *= 1.2f;
            return c;
        }

        // ------------------------------------------------------------------ jefes
        /// <summary>Gorō, el Martillo de Kodoyama (Minijefe): lento, golpes enormes, giro imparable que lo marea.</summary>
        public static EnemyConfig Goro()
        {
            var c = new EnemyConfig
            {
                id = "goro", displayName = "Gorō", maxHealth = 520, runSpeed = 3.8f, walkSpeed = 2f, turnSpeed = 5f,
                radius = 1.0f, height = 3.2f, scale = 1f, maxImbalance = 4, exhaustedTime = 4f, guardTime = 0.6f,
                poiseHits = 5, hyperArmor = true, knockbackResist = 0.9f, preferredDistance = 4.2f, detectRadius = 30f, loseRadius = 80f,
                finisherHealth = 0.12f, attackCooldown = new Vector2(0.9f, 1.8f),
                animGuard = "Idle", animCounter = "Combo1", animExhausted = "StunSpin", animHit = "Parried",
                animSpotted = "Spotted", animDeath = "StunSpin", animParried = "Parried",
            };
            var c1 = Hit("Combo1", 22, 0.48f, 0.62f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, telegraph: 0.2f, kb: 1.8f);
            var c2 = Hit("Combo2", 24, 0.5f, 0.64f, range: 3.4f, arc: 130, kind: AttackKind.Heavy, lunge: 1.2f, kb: 1.8f);
            var c3 = Hit("Combo3", 28, 0.45f, 0.62f, range: 3.6f, arc: 160, kind: AttackKind.Heavy, lunge: 1.0f, kb: 2.4f);
            var slam = Hit("Heavy", 38, 0.55f, 0.62f, range: 3.4f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.5f, telegraph: 0.3f, kb: 3f);
            slam.special = "slam"; slam.specialParam = 4.6f;
            var spin = Hit("Spin", 20, 0.2f, 0.85f, range: 2.8f, arc: 360, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.35f, kb: 2.5f);
            spin.special = "spin"; spin.specialParam = 3.8f;
            var slam2 = slam.Clone(); slam2.specialParam = 6f; slam2.damage = 42;
            c.patterns = new[]
            {
                new AttackPattern { name = "Martillazo", steps = new[] { c1 }, weight = 1.2f, maxRange = 4f },
                new AttackPattern { name = "Doble martillazo", steps = new[] { c1, c2 }, weight = 1.5f, maxRange = 4f },
                new AttackPattern { name = "Combo completo", steps = new[] { c1, c2, c3 }, weight = 1.2f, maxRange = 4f, minPhase = 0 },
                new AttackPattern { name = "Golpe sísmico", steps = new[] { slam }, weight = 1f, maxRange = 5f, cooldown = 6f },
                new AttackPattern { name = "Torbellino", steps = new[] { spin }, weight = 1f, maxRange = 9f, cooldown = 9f, exhaustAfter = true },
                new AttackPattern { name = "Terremoto", steps = new[] { c1, slam2 }, weight = 1.3f, maxRange = 5f, cooldown = 7f, minPhase = 1 },
            };
            return c;
        }

        /// <summary>Mizuchi, la Marea (jefe del lago): ninja veloz que lanza olas y llama refuerzos.</summary>
        public static EnemyConfig Mizuchi()
        {
            var c = Ninja();
            c.id = "mizuchi"; c.displayName = "Mizuchi"; c.maxHealth = 420; c.scale = 1.3f; c.runSpeed = 6.2f;
            c.maxImbalance = 5; c.exhaustedTime = 3f; c.guardTime = 1.6f; c.poiseHits = 2; c.detectRadius = 30; c.loseRadius = 80;
            c.finisherHealth = 0.12f; c.tint = new Color(0.2f, 0.65f, 0.8f); c.tintStrength = 0.5f; c.hyperArmor = false;
            var a1 = Hit("Attack1", 16, 0.6f, 0.78f, telegraph: 0.08f, speed: 1.15f);
            var a2 = Hit("Attack2", 16, 0.42f, 0.62f, speed: 1.15f);
            var a3 = Hit("Attack3", 20, 0.5f, 0.7f, kind: AttackKind.Heavy, lunge: 1.6f, speed: 1.1f, kb: 1.5f);
            var wave = Hit("Attack3", 18, 0.5f, 0.6f, kind: AttackKind.Light, lunge: 0f, telegraph: 0.25f);
            wave.special = "wave"; wave.specialParam = 1;
            var wave3 = wave.Clone(); wave3.specialParam = 3;
            var summon = Hit("Spotted", 0, 0.5f, 0.55f, lunge: 0f); summon.special = "summon"; summon.specialParam = 2;
            var tp = Hit("Attack2", 0, 0.3f, 0.35f, lunge: 0f); tp.special = "teleport"; tp.specialParam = 2.4f;
            c.patterns = new[]
            {
                new AttackPattern { name = "Marea", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 3f },
                new AttackPattern { name = "Ola", steps = new[] { wave }, weight = 1.3f, minRange = 4f, maxRange = 16f, cooldown = 3f },
                new AttackPattern { name = "Tres olas", steps = new[] { wave3, wave }, weight = 1.2f, minRange = 3f, maxRange = 16f, cooldown = 6f, minPhase = 1 },
                new AttackPattern { name = "Corriente", steps = new[] { tp, a1, a2 }, weight = 1f, maxRange = 12f, cooldown = 7f, minPhase = 1 },
                new AttackPattern { name = "Llamado", steps = new[] { summon }, weight = 0.8f, maxRange = 20f, cooldown = 25f, minPhase = 1 },
            };
            return c;
        }

        /// <summary>Ōzeki, el Gran Campeón (bosque de bambú): sumo gigante, embestidas y pisotones.</summary>
        public static EnemyConfig Ozeki()
        {
            var c = Sumo();
            c.id = "ozeki"; c.displayName = "Ōzeki"; c.maxHealth = 560; c.scale = 1.35f; c.maxImbalance = 3;
            c.detectRadius = 30; c.loseRadius = 80; c.finisherHealth = 0.12f; c.exhaustedTime = 4.5f;
            c.tint = new Color(0.55f, 0.15f, 0.12f); c.tintStrength = 0.35f;
            var slap1 = Hit("Attack1", 22, 0.7f, 0.9f, range: 3.2f, arc: 130, kind: AttackKind.Heavy, lunge: 0.8f, kb: 2f);
            var slap2 = Hit("Attack2", 24, 0.6f, 0.82f, range: 3.2f, arc: 130, kind: AttackKind.Heavy, lunge: 0.8f, kb: 2f);
            var stomp = Hit("Attack3", 30, 0.8f, 0.92f, range: 3.6f, arc: 360, kind: AttackKind.Unblockable, lunge: 0.2f, telegraph: 0.25f, kb: 3f);
            stomp.special = "slam"; stomp.specialParam = 5f;
            var charge = Hit("Special", 32, 0.35f, 0.85f, range: 2.6f, arc: 90, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.4f, kb: 3.5f);
            charge.special = "charge"; charge.specialParam = 13f;
            c.patterns = new[]
            {
                new AttackPattern { name = "Bofetadas", steps = new[] { slap1, slap2 }, weight = 2f, maxRange = 3.8f },
                new AttackPattern { name = "Triple bofetada", steps = new[] { slap1, slap2, slap1 }, weight = 1.2f, maxRange = 3.8f, minPhase = 1 },
                new AttackPattern { name = "Pisotón sísmico", steps = new[] { stomp }, weight = 1f, maxRange = 5f, cooldown = 5f },
                new AttackPattern { name = "Embestida", steps = new[] { charge }, weight = 1.3f, minRange = 4f, maxRange = 16f, cooldown = 4f },
                new AttackPattern { name = "Doble embestida", steps = new[] { charge, charge }, weight = 1f, minRange = 4f, maxRange = 16f, cooldown = 8f, minPhase = 1 },
            };
            return c;
        }

        /// <summary>Kage, la Sombra (jefe final): espejo de Kaito. Rápido, desvía mucho, se teletransporta y crea clones.</summary>
        public static EnemyConfig Kage()
        {
            var c = new EnemyConfig
            {
                id = "kage", displayName = "Kage", maxHealth = 600, runSpeed = 6.8f, walkSpeed = 2.6f, turnSpeed = 14f,
                radius = 0.4f, height = 1.6f, scale = 1.05f, maxImbalance = 5, exhaustedTime = 2.6f, guardTime = 1.8f,
                poiseHits = 1, preferredDistance = 3.2f, detectRadius = 30f, loseRadius = 80f, finisherHealth = 0.1f,
                attackCooldown = new Vector2(0.35f, 1.0f),
                tint = new Color(0.12f, 0.08f, 0.2f), tintStrength = 0.8f,
                animGuard = "ParryStance", animCounter = "ParrySuccess", animExhausted = "Blocked", animHit = "Hit",
                animSpotted = "Blocked", animDeath = "Hit", animParried = "Blocked",
            };
            var a1 = Hit("Attack1", 14, 0.3f, 0.6f, range: 2.4f, telegraph: 0.14f, speed: 0.9f);
            var a2 = Hit("Attack2", 14, 0.25f, 0.6f, range: 2.4f, telegraph: 0.1f, speed: 0.9f);
            var a3 = Hit("Attack3", 20, 0.22f, 0.45f, range: 2.7f, kind: AttackKind.Heavy, lunge: 1.8f, telegraph: 0.16f, speed: 0.9f, kb: 1.6f);
            var tp = Hit("Dash", 0, 0.2f, 0.25f, lunge: 0f); tp.special = "teleport"; tp.specialParam = 2.2f;
            var ws = Hit("Attack3", 30, 0.3f, 0.35f, kind: AttackKind.Unblockable, lunge: 0f, telegraph: 0.5f, kb: 2f);
            ws.special = "windslash"; ws.specialParam = 10f;
            var clones = Hit("ParrySuccess", 0, 0.5f, 0.55f, lunge: 0f); clones.special = "clones"; clones.specialParam = 2;
            c.patterns = new[]
            {
                new AttackPattern { name = "Espejo", steps = new[] { a1, a2, a3 }, weight = 2f, maxRange = 3f },
                new AttackPattern { name = "Rápido", steps = new[] { a1, a2 }, weight = 1.5f, maxRange = 3f },
                new AttackPattern { name = "Sombra", steps = new[] { tp, a1, a2, a3 }, weight = 1.2f, maxRange = 14f, cooldown = 5f },
                new AttackPattern { name = "Corte del Vacío", steps = new[] { ws }, weight = 1.1f, minRange = 3f, maxRange = 12f, cooldown = 6f },
                new AttackPattern { name = "Clones", steps = new[] { clones }, weight = 1f, maxRange = 20f, cooldown = 22f, minPhase = 1 },
                new AttackPattern { name = "Furia sombría", steps = new[] { a1, a2, a1, a2, a3 }, weight = 1.3f, maxRange = 3f, minPhase = 1 },
            };
            return c;
        }

        public static EnemyConfig KageClone()
        {
            var c = Kage();
            c.id = "kage_clone"; c.displayName = "Sombra"; c.maxHealth = 1; c.poiseHits = 99; c.guardTime = 0.1f;
            c.tint = new Color(0.25f, 0.1f, 0.4f); c.tintStrength = 0.9f; c.scale = 1f; c.detectRadius = 40f;
            var a1 = Hit("Attack1", 10, 0.3f, 0.6f, range: 2.4f, telegraph: 0.2f, speed: 0.85f);
            var a3 = Hit("Attack3", 12, 0.22f, 0.45f, range: 2.7f, lunge: 1.6f, telegraph: 0.2f, speed: 0.85f);
            c.patterns = new[] { new AttackPattern { name = "Eco", steps = new[] { a1, a3 }, weight = 1f, maxRange = 3f } };
            return c;
        }
    }
}
