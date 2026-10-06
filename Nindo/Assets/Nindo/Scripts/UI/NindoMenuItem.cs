using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Cómo se ve el ítem elegido de un menú (botón, fila de opciones): entra un kunai dorado de cursor que cada
    /// tanto "pincha" hacia el texto, y la letra pasa de gris apagado a papel y crece un poco. Un solo indicador:
    /// la cinta roja que había detrás se confundía con la bandana de la vida y repetía lo que ya dice el kunai.
    /// Reemplaza al tinte de color del Button de Unity: con teclado o mando el elegido quedaba MÁS oscuro
    /// que los demás (luma 0.076 contra 0.087) y no había forma de saber dónde estaba el foco.
    /// Va en el mismo GameObject que el Selectable (recibe sus eventos de selección).
    /// </summary>
    public class NindoMenuItem : MonoBehaviour, ISelectHandler, IDeselectHandler, IPointerEnterHandler, ISubmitHandler, IPointerClickHandler
    {
        public RectTransform cursor;          // kunai
        public Image cursorImage;
        public TextMeshProUGUI label;
        public Vector2 cursorPos;
        public float gap = 64f;              // del centro del kunai al comienzo del texto (la punta queda a ~20 px)
        // los no elegidos bien apagados: sin la cinta, el contraste de la letra es lo que separa al elegido
        public Color labelNormal = new Color(0.62f, 0.59f, 0.53f, 1f);
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
            if (Mathf.Approximately(k, target) && punch <= 0f && !selected) return;
            // entra en 0.12 s y sale en 0.08 s (el que se va no tiene que distraer)
            k = Mathf.MoveTowards(k, target, dt / (selected ? UIAnim.Fast : 0.08f));
            punch = Mathf.MoveTowards(punch, 0f, dt / 0.18f);
            Apply();
        }

        /// <summary>
        /// El kunai apunta al comienzo de la palabra (a 'gap' px), no al borde del ítem: en la pausa quedaba a
        /// 130 px del texto, pegado al borde de la pantalla, y no se entendía qué señalaba. Sirve igual para
        /// textos alineados a la izquierda o centrados (menú principal).
        /// </summary>
        Vector2 CursorHome()
        {
            if (label == null) return cursorPos;
            var lr = label.rectTransform;
            float start = lr.offsetMin.x;
            if (label.alignment == TMPro.TextAlignmentOptions.Center || label.alignment == TMPro.TextAlignmentOptions.Midline)
                start += Mathf.Max(0f, (lr.rect.width - label.preferredWidth) * 0.5f);
            return new Vector2(start - gap, cursorPos.y);
        }

        void Apply()
        {
            float e = selected ? UIAnim.OutCubic(k) : k * k;
            if (cursor != null)
            {
                // entra desde 24 px a la izquierda; elegido, pincha 6 px hacia el texto cada 1.1 s (atrae la vista
                // sin vibrar todo el tiempo)
                float poke = selected ? Mathf.Pow(Mathf.Max(0f, Mathf.Sin(Time.unscaledTime * Mathf.PI * 2f / 1.1f)), 6f) * 6f : 0f;
                cursor.anchoredPosition = CursorHome() + new Vector2(-24f * (1f - e) + poke * e, 0f);
                var c = cursorImage.color; c.a = e; cursorImage.color = c;
                cursorImage.enabled = e > 0.001f;
            }
            if (label != null)
            {
                label.color = Color.Lerp(labelNormal, labelSelected, e);
                // al confirmar: se hunde y vuelve
                float press = punch > 0f ? Mathf.Sin(punch * Mathf.PI) * 0.08f : 0f;
                label.rectTransform.localScale = Vector3.one * (1f + 0.07f * e - press);
            }
        }
    }
}
