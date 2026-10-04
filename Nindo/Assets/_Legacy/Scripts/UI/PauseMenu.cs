using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

public class PauseMenu : MonoBehaviour
{
    [SerializeField] bool GameIsPaused = false;
    [SerializeField] private GameObject Canvas;
    [SerializeField] private GameObject HUD;

    private void Awake()
    {
        Canvas.SetActive(false);
    }
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Escape))
        {
            if (GameIsPaused)
            {
                Resume();
            }
            else
            {
                Pause();
            }
        }
    }

    public void Resume()
    {
        Canvas.SetActive(false);
        Time.timeScale = 1f;
        HUD.SetActive(true);
        GameIsPaused = false;
    }
    void Pause()
    {
        Canvas.SetActive(true);
        Time.timeScale = 0f;
        HUD.SetActive(false);
        GameIsPaused = true;
    }

    public void LoadMenu()
    {
        Time.timeScale = 1f;
        SceneManager.LoadScene("Menu");
    }
    public void Quit()
    {
        Application.Quit();
    }
}
