using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Nindo
{
    [Serializable]
    public class SaveData
    {
        public int version = 1;
        public string checkpoint = "";            // id del último santuario
        public List<string> flags = new List<string>();
        public bool[] seals = new bool[3];
        public float playTime;
        public int deaths;

        public bool HasFlag(string f) => flags.Contains(f);
        public void SetFlag(string f)
        {
            if (string.IsNullOrEmpty(f) || flags.Contains(f)) return;
            flags.Add(f);
            GameEvents.RaiseFlag(f);
        }
        public bool HasSeal(SealId s) => seals != null && seals.Length > (int)s && seals[(int)s];
        public int SealCount
        {
            get { int n = 0; if (seals != null) foreach (var s in seals) if (s) n++; return n; }
        }
    }

    /// <summary>Guardado en JSON (Application.persistentDataPath/nindo_save.json).</summary>
    public static class SaveSystem
    {
        static SaveData data;
        static string PathFile => System.IO.Path.Combine(Application.persistentDataPath, "nindo_save.json");

        public static SaveData Data
        {
            get { if (data == null) data = new SaveData(); return data; }
        }

        public static bool HasSave => File.Exists(PathFile);

        public static void NewGame()
        {
            data = new SaveData();
        }

        public static bool Load()
        {
            try
            {
                if (!File.Exists(PathFile)) { data = new SaveData(); return false; }
                data = JsonUtility.FromJson<SaveData>(File.ReadAllText(PathFile)) ?? new SaveData();
                if (data.seals == null || data.seals.Length != 3) data.seals = new bool[3];
                return true;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Nindo] No se pudo leer la partida: " + e.Message);
                data = new SaveData();
                return false;
            }
        }

        public static void Save()
        {
            try { File.WriteAllText(PathFile, JsonUtility.ToJson(Data, true)); }
            catch (Exception e) { Debug.LogWarning("[Nindo] No se pudo guardar: " + e.Message); }
        }

        public static void Delete()
        {
            try { if (File.Exists(PathFile)) File.Delete(PathFile); } catch { }
            data = new SaveData();
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { data = null; }
    }

    /// <summary>Opciones del jugador (PlayerPrefs).</summary>
    public static class Settings
    {
        public static float MasterVolume { get => PlayerPrefs.GetFloat("nindo.master", 0.9f); set => PlayerPrefs.SetFloat("nindo.master", value); }
        public static float MusicVolume { get => PlayerPrefs.GetFloat("nindo.music", 0.6f); set => PlayerPrefs.SetFloat("nindo.music", value); }
        public static float SfxVolume { get => PlayerPrefs.GetFloat("nindo.sfx", 0.9f); set => PlayerPrefs.SetFloat("nindo.sfx", value); }
        public static float ScreenShake { get => PlayerPrefs.GetFloat("nindo.shake", 1f); set => PlayerPrefs.SetFloat("nindo.shake", value); }
        public static bool SlowMotionEnabled { get => PlayerPrefs.GetInt("nindo.slowmo", 1) == 1; set => PlayerPrefs.SetInt("nindo.slowmo", value ? 1 : 0); }
        public static bool Rumble { get => PlayerPrefs.GetInt("nindo.rumble", 1) == 1; set => PlayerPrefs.SetInt("nindo.rumble", value ? 1 : 0); }
        public static int Quality { get => PlayerPrefs.GetInt("nindo.quality", -1); set => PlayerPrefs.SetInt("nindo.quality", value); }
        public static bool Fullscreen { get => Screen.fullScreen; set => Screen.fullScreen = value; }
        public static void Save() => PlayerPrefs.Save();
    }
}
