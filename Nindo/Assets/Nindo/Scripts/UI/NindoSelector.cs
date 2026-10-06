using System;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Nindo
{
    /// <summary>
    /// Fila de opciones "‹ valor ›" que cambia con izquierda/derecha (teclado o mando) o con clic en las
    /// flechas; arriba/abajo navegan como siempre. Antes las opciones se cambiaban apretando el botón y con el
    /// mando había que ciclar todas para volver una atrás.
    /// </summary>
    public class NindoSelector : Selectable, ISubmitHandler, IPointerClickHandler
    {
        public string[] options = new string[0];
        public int index;
        public TextMeshProUGUI valueText;
        public RectTransform leftArrow, rightArrow;
        public Action<int> onChange;
        float nudge, nudgeDir;

        public void SetIndex(int i, bool notify)
        {
            if (options.Length == 0) return;
            index = (i % options.Length + options.Length) % options.Length;
            if (valueText != null) valueText.text = options[index];
            if (notify) onChange?.Invoke(index);
        }

        public void Step(int dir)
        {
            SetIndex(index + dir, true);
            nudge = 1f; nudgeDir = dir;
            Game.Audio?.Play("ui_move", null, 0.35f);
        }

        public override void OnMove(AxisEventData e)
        {
            if (e.moveDir == MoveDirection.Left) { Step(-1); return; }
            if (e.moveDir == MoveDirection.Right) { Step(1); return; }
            base.OnMove(e);
        }

        // Enter / A también avanzan (lo esperable en una opción de dos valores como "Sí / No")
        public void OnSubmit(BaseEventData e) => Step(1);

        public override void OnPointerDown(PointerEventData e)
        {
            base.OnPointerDown(e);
            EventSystem.current?.SetSelectedGameObject(gameObject);
        }

        public void OnPointerClick(PointerEventData e)
        {
            // clic en la mitad izquierda de la fila = atrás, derecha = adelante
            if (valueText == null) { Step(1); return; }
            RectTransformUtility.ScreenPointToLocalPointInRectangle(valueText.rectTransform, e.position, e.pressEventCamera, out var local);
            Step(local.x < 0f ? -1 : 1);
        }

        void Update()
        {
            if (nudge <= 0f) return;
            // la flecha que se usó empuja hacia afuera y vuelve
            nudge = Mathf.MoveTowards(nudge, 0f, Time.unscaledDeltaTime / 0.16f);
            float off = Mathf.Sin(nudge * Mathf.PI) * 8f;
            var arrow = nudgeDir < 0 ? leftArrow : rightArrow;
            if (arrow != null) arrow.localScale = Vector3.one * (1f + off * 0.03f);
            if (valueText != null) valueText.rectTransform.anchoredPosition = new Vector2(off * nudgeDir * 0.5f, 0f);
        }
    }
}
