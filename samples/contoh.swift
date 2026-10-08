import UIKit

// Buka file ini di Notepad, lalu pindah baris pakai panah atas/bawah.
class ProfileViewController: UIViewController {
    var names: [String] = ["Budi", "Sari"]

    override func viewDidLoad() {
        super.viewDidLoad()
        if let user = currentUser {
            label.text = "Halo {nama}"   // kurung di dalam string nggak dihitung
            load(user,
                 animated: true,
                 completion: { result in
                     print(result)
                 })
        }
    }

    func load(_ user: User, animated: Bool, completion: (Result) -> Void) {
        for name in names {
            print(name)
        }
    }
}
