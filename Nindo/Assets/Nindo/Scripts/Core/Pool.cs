using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Nindo
{
    /// <summary>
    /// Pool genérico de GameObjects por prefab. Evita Instantiate/Destroy en combate
    /// (antes cada dash creaba decenas de meshes y cada VFX se destruía con Destroy(go, 2f)).
    /// </summary>
    public static class Pool
    {
        class Entry
        {
            public GameObject prefab;
            public readonly Stack<GameObject> free = new Stack<GameObject>();
        }

        static readonly Dictionary<int, Entry> pools = new Dictionary<int, Entry>();
        static readonly Dictionary<int, int> instanceToPrefab = new Dictionary<int, int>();
        static Transform root;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset()
        {
            pools.Clear(); instanceToPrefab.Clear(); root = null;
            SceneManager.sceneUnloaded -= OnSceneUnloaded;
            SceneManager.sceneUnloaded += OnSceneUnloaded;
        }

        /// <summary>
        /// Las plantillas de FX se destruyen con la escena (y el [Pool] también): se olvidan sus pools
        /// y las instancias que apuntaban a ellos, si no cada Menú → Juego deja entradas muertas.
        /// Solo se borran las de plantillas ya destruidas, así no importa el orden con la escena nueva.
        /// </summary>
        static void OnSceneUnloaded(Scene s)
        {
            List<int> dead = null;
            foreach (var kv in pools)
                if (kv.Value.prefab == null) (dead ??= new List<int>()).Add(kv.Key);
            if (dead == null) return;
            foreach (int k in dead) pools.Remove(k);
            var orphans = new List<int>();
            foreach (var kv in instanceToPrefab)
                if (!pools.ContainsKey(kv.Value)) orphans.Add(kv.Key);
            foreach (int k in orphans) instanceToPrefab.Remove(k);
        }

        static Transform Root
        {
            get
            {
                if (root == null)
                {
                    var go = new GameObject("[Pool]");
                    root = go.transform;
                }
                return root;
            }
        }

        public static GameObject Spawn(GameObject prefab, Vector3 pos, Quaternion rot, Transform parent = null)
        {
            if (prefab == null) return null;
            int key = prefab.GetInstanceID();
            if (!pools.TryGetValue(key, out var e)) { e = new Entry { prefab = prefab }; pools[key] = e; }
            GameObject go = null;
            while (e.free.Count > 0 && go == null) go = e.free.Pop();
            if (go == null)
            {
                go = Object.Instantiate(prefab, pos, rot, parent);
                instanceToPrefab[go.GetInstanceID()] = key;
            }
            else
            {
                go.transform.SetParent(parent, false);
                go.transform.SetPositionAndRotation(pos, rot);
                go.SetActive(true);
            }
            return go;
        }

        public static void Despawn(GameObject go)
        {
            if (go == null) return;
            if (!instanceToPrefab.TryGetValue(go.GetInstanceID(), out int key))
            {
                Object.Destroy(go);
                return;
            }
            go.SetActive(false);
            go.transform.SetParent(Root, false);
            pools[key].free.Push(go);
        }

        /// <summary>Devuelve el objeto al pool después de 'seconds' (tiempo escalado).</summary>
        public static void Despawn(GameObject go, float seconds)
        {
            if (go == null) return;
            var d = go.GetComponent<AutoDespawn>();
            if (d == null) d = go.AddComponent<AutoDespawn>();
            d.Arm(seconds);
        }
    }

    public class AutoDespawn : MonoBehaviour
    {
        float t;
        public void Arm(float seconds) { t = seconds; enabled = true; }
        void Update()
        {
            t -= Time.deltaTime;
            if (t <= 0f) { enabled = false; Pool.Despawn(gameObject); }
        }
    }
}
