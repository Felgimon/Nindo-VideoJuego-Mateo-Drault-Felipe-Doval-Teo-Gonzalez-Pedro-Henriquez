using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class DesequilibroBar : MonoBehaviour
{
    [SerializeField] private Transform target;
    [SerializeField] private Vector3 offSet;
    [SerializeField] private Image greyBar;


    // Start is called before the first frame update
    void Start()
    {

    }

    // Update is called once per frame
    void Update()
    {
        transform.position = target.position + offSet;
    }

    public void UpdateDesequilibrioBar(float maxMomentum, float momentum)
    {
        greyBar.fillAmount = momentum / maxMomentum;
    }
}
