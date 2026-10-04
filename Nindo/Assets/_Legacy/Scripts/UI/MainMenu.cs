using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class MainMenu : MonoBehaviour
{
    [SerializeField] private Image nindoBackground;
    [SerializeField] private Sprite nindoOpenEyes;

    [SerializeField] private CanvasGroup menuButtons; 
    [SerializeField] private float fadeDuration = 3f;
    [SerializeField] private CanvasGroup Title;

    public void PlayGame()
    {
        menuButtons.blocksRaycasts = false; // para que no reciban eventos
        EventSystem.current?.SetSelectedGameObject(null); // deselecciono cualquier botón seleccionado
        StartCoroutine(ChangeBackgroundSmooth());

    }

    private IEnumerator ChangeBackgroundSmooth()
    {

    Transform parent = nindoBackground.transform.parent;
    if (parent == null)
    {
        var canvas = nindoBackground.GetComponentInParent<Canvas>();
        if (canvas != null) parent = canvas.transform;
    }

    // Crear GameObject con componentes UI básicos
    Image fadeImage = new GameObject("FadeImage", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image)).GetComponent<Image>();

    // Parentear (si hay parent)
    if (parent != null)
    {
        fadeImage.transform.SetParent(parent, false); // false para no alterar escala/pos
        int targetIndex = menuButtons.transform.GetSiblingIndex();
        fadeImage.transform.SetSiblingIndex(targetIndex);
        }

        // Asignar sprite y properties
    fadeImage.sprite = nindoOpenEyes;
    fadeImage.raycastTarget = false;
    fadeImage.color = new Color(1f, 1f, 1f, 0f);

    // Copiar rect transform del background (para que tenga mismo tamaño/anchos)
    fadeImage.rectTransform.sizeDelta = nindoBackground.rectTransform.sizeDelta;
    fadeImage.GetComponent<RectTransform>().anchorMin = nindoBackground.rectTransform.anchorMin;
    fadeImage.GetComponent<RectTransform>().anchorMax = nindoBackground.rectTransform.anchorMax;
    // Fade in de la nueva imagen, fade out del background actual y de los botones
    float t = 0f;
    while (t < fadeDuration)
        {
            t += Time.deltaTime;
            float alpha = t / fadeDuration; // de 0 a 1
            menuButtons.alpha = 1f - 5*alpha; // fade out de los botones
            nindoBackground.color = new Color(1, 1, 1, 1f - alpha); // fade out del background actual
            Title.alpha = alpha; // fade in del título
            fadeImage.color = new Color(1, 1, 1, alpha); // fade in de la nueva imagen
            yield return null;
        }

    // Lo termino
    yield return new WaitForSeconds(1f); // esperar un poquito más antes de empezar el juego
    SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex + 1);
    }

    public void QuitGame()
    {
        Debug.Log("QUIT");
        Application.Quit();
    }
}

