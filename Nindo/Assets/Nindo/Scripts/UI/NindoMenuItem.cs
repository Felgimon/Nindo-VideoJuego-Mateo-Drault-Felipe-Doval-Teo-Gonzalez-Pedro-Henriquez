using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Cómo se ve el ítem elegido de un menú (botón, fila de opciones): una cinta roja de bandana se desenrolla
    /// detrás del texto, entra un kunai dorado de cursor y la letra pasa de gris a papel y crece un poco.
    /// Reemplaza al tinte de color del Button de Unity: con teclado o mando el elegido quedaba MÁS oscuro
    /// que los demás (luma 0.076 contra 0.087) y no había forma de saber dónde estaba el foco.
    /// Va en el mismo GameObject que el Selectable (recibe sus eventos de selección).
    /// </summary>
    public class NindoMenuItem : MonoBehaviour, ISelectHandler, IDeselectHandler, IPointerEnterHandler, ISubmitHandler, IPointerClickHandler
    {
        public RectTransform ribbon;          // Image Sliced con pivote a la izquierda: se le anima el ancho
        public Image ribbonImage;
        public RectTransform cursor;          // kunai
        public Image cursorImage;
        public TextMeshProUGUI label;
        public float ribbonWidth = 470f, ribbonMin = 90f;
        public Vector2 cursorPos;
        public Color labelNormal = new Color(0.78f, 0.74f, 0.66f, 1f);
        public Color labelSelected = UIFactory.Paper;
        public bool silent;                    // sin sonido de "mover" (la primera selección al abrir un panel)

        bool selected;
        float k, punch;

        public bool IsSelected => selected;

        // al volver a mostrar el panel el EventSystem puede seguir apuntando a este ítem
        void OnEnable() => Refresh();

        /// <summary>
        /// Toma el estado de selección de ahora, sin animar. UIFactory.AttachFocus la llama al terminar de armar
        /// el ítem: el AddComponent sobre un objeto activo corre OnEnable antes de que existan la cinta y el kunai,
        /// y en un panel que ya está a la vista (el menú principal) todos los ítems arrancaban con la cinta puesta.
        /// </summary>
        public void Refresh()
        {
            selected = EventSystem.current != null && EventSystem.current.currentSelectedGameObject == gameObject;
            k = selected ? 1f : 0f;
            punch = 0f;
            Apply();
        }

        public void OnSelect(BaseEventData e)
        {
            if (!selected && !silent) Game.Audio?.Play("ui_move", null, 0.35f);
            silent = false;
            selected = true;
        }

        public void OnDeselect(BaseEventData e) => selected = false;

        public void OnPointerEnter(PointerEventData e)
        {
            var sel = GetComponent<Selectable>();
            if (sel != null && sel.IsInteractable()) EventSystem.current?.SetSelectedGameObject(gameObject);
        }

        public void OnSubmit(BaseEventData e) => punch = 1f;
        public void OnPointerClick(PointerEventData e) => punch = 1f;

        void Update()
        {
            float dt = Time.unscaledDeltaTime;
            float target = selected ? 1f : 0f;
            if (Mathf.Approximately(k, target) && punch <= 0f) return;
            // entra en 0.12 s y sale en 0.08 s (el que se va no tiene que distraer)
            k = Mathf.MoveTowards(k, target, dt / (selected ? UIAnim.Fast : 0.08f));
            punch = Mathf.MoveTowards(punch, 0f, dt / 0.18f);
            Apply();
        }

        void Apply()
        {
            float e = selected ? UIAnim.OutCubic(k) : k * k;
            if (ribbon != null)
            {
                ribbon.sizeDelta = new Vector2(Mathf.Lerp(ribbonMin, ribbonWidth, e), ribbon.sizeDelta.y);
                var c = ribbonImage.color; c.a = Mathf.Clamp01(e * 1.6f); ribbonImage.color = c;
                ribbonImage.enabled = e > 0.001f;
            }
            if (cursor != null)
            {
                cursor.anchoredPosition = cursorPos + new Vector2(-20f * (1f - e), 0f);
                var c = cursorImage.color; c.a = e; cursorImage.color = c;
                cursorImage.enabled = e > 0.001f;
            }
            if (label != null)
            {
                label.color = Color.Lerp(labelNormal, labelSelected, e);
                // al confirmar: se hunde y vuelve
                float press = punch > 0f ? Mathf.Sin(punch * Mathf.PI) * 0.08f : 0f;
                label.rectTransform.localScale = Vector3.one * (1f + 0.06f * e - press);
            }
        }
    }
}
