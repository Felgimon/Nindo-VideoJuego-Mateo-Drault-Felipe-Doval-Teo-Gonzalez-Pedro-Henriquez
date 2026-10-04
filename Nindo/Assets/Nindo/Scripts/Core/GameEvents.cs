using System;

namespace Nindo
{
    public enum SealId { Montana = 0, Lago = 1, Bambu = 2 }

    /// <summary>Bus de eventos global. Los sistemas se comunican sin referencias directas.</summary>
    public static class GameEvents
    {
        public static event Action<Enemy> EnemyKilled;
        public static event Action<Enemy, bool> EnemyFinished;          // (enemigo, fue con finisher)
        public static event Action<bool> Parry;                           // perfecto?
        public static event Action<float> PlayerDamaged;                  // daño
        public static event Action PlayerDied;
        public static event Action PlayerRespawned;
        public static event Action<string> CheckpointActivated;
        public static event Action<SealId> SealObtained;
        public static event Action<Boss> BossStarted;
        public static event Action<Boss> BossDefeated;
        public static event Action<Zone> ZoneEntered;
        public static event Action<bool> CombatStateChanged;               // en combate?
        public static event Action<string> FlagSet;
        public static event Action<string> StoryTrigger;                   // triggers del mapa
        public static event Action<int> AbilityUsed;

        public static void RaiseEnemyKilled(Enemy e) => EnemyKilled?.Invoke(e);
        public static void RaiseEnemyFinished(Enemy e, bool finisher) => EnemyFinished?.Invoke(e, finisher);
        public static void RaiseParry(bool perfect) => Parry?.Invoke(perfect);
        public static void RaisePlayerDamaged(float dmg) => PlayerDamaged?.Invoke(dmg);
        public static void RaisePlayerDied() => PlayerDied?.Invoke();
        public static void RaisePlayerRespawned() => PlayerRespawned?.Invoke();
        public static void RaiseCheckpoint(string id) => CheckpointActivated?.Invoke(id);
        public static void RaiseSeal(SealId s) => SealObtained?.Invoke(s);
        public static void RaiseBossStarted(Boss b) => BossStarted?.Invoke(b);
        public static void RaiseBossDefeated(Boss b) => BossDefeated?.Invoke(b);
        public static void RaiseZoneEntered(Zone z) => ZoneEntered?.Invoke(z);
        public static void RaiseCombatState(bool inCombat) => CombatStateChanged?.Invoke(inCombat);
        public static void RaiseFlag(string f) => FlagSet?.Invoke(f);
        public static void RaiseStoryTrigger(string id) => StoryTrigger?.Invoke(id);
        public static void RaiseAbility(int index) => AbilityUsed?.Invoke(index);

        public static void Clear()
        {
            EnemyKilled = null; EnemyFinished = null; Parry = null; PlayerDamaged = null; PlayerDied = null;
            PlayerRespawned = null; CheckpointActivated = null; SealObtained = null; BossStarted = null;
            BossDefeated = null; ZoneEntered = null; CombatStateChanged = null; FlagSet = null;
            StoryTrigger = null; AbilityUsed = null;
        }
    }
}
